from __future__ import annotations

import fcntl
import hashlib
import html
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .naming import slugify_filename
from .manifest import SyncManifest, SyncManifestNote
from .model import MODEL_NAME, create_notetype, load_css, require_notetype


class SyncSafetyError(RuntimeError):
    """An operation was refused to protect collection/review data."""


class DuplicateIdentityError(RuntimeError):
    """An immutable Acervo note identity occurs more than once in Anki."""


@dataclass(frozen=True)
class RobotSettings:
    endpoint: str
    username: str
    password: str
    collection_path: Path
    backup_dir: Path
    template_dir: Path
    media_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.endpoint.endswith("/"):
            raise ValueError("The Anki sync endpoint must end with a trailing slash")
        if not self.username or not self.password:
            raise ValueError("Anki sync username and password are required")


def _sync_requirement_name(output: Any) -> str:
    names = {
        output.NO_CHANGES: "NO_CHANGES",
        output.NORMAL_SYNC: "NORMAL_SYNC",
        output.FULL_SYNC: "FULL_SYNC",
        output.FULL_DOWNLOAD: "FULL_DOWNLOAD",
        output.FULL_UPLOAD: "FULL_UPLOAD",
    }
    return names.get(output.required, f"UNKNOWN({output.required})")


class AnkiRobot:
    """A persistent headless Anki client that synchronizes before it mutates."""

    def __init__(self, settings: RobotSettings):
        self.settings = settings
        self.css = load_css(settings.template_dir)

    @contextmanager
    def _exclusive_collection(self) -> Iterator[None]:
        self.settings.collection_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.settings.collection_path.parent / ".acervo-anki-robot.lock"
        with lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SyncSafetyError("Another Anki robot process is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _open_collection(self) -> Any:
        from anki.collection import Collection

        return Collection(str(self.settings.collection_path))

    def _login(self, collection: Any) -> Any:
        return collection.sync_login(
            self.settings.username,
            self.settings.password,
            self.settings.endpoint,
        )

    def _wait_for_media(self, collection: Any) -> None:
        deadline = time.monotonic() + self.settings.media_timeout_seconds
        while True:
            status = collection.media_sync_status()
            if not status.active:
                return
            if time.monotonic() >= deadline:
                collection.abort_media_sync()
                raise TimeoutError("Anki media synchronization did not finish in time")
            time.sleep(0.1)

    def _normal_sync(self, collection: Any, auth: Any, *, stage: str) -> Any:
        output = collection.sync_collection(auth, sync_media=True)
        if output.required != output.NO_CHANGES:
            raise SyncSafetyError(
                f"{stage} requires {_sync_requirement_name(output)}; "
                "the robot will never choose a full-sync direction automatically"
            )
        self._wait_for_media(collection)
        return output

    def _backup(self, collection: Any) -> bool:
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        return bool(
            collection.create_backup(
                backup_folder=str(self.settings.backup_dir),
                force=True,
                wait_for_completion=True,
            )
        )

    @staticmethod
    def _close(collection: Any) -> None:
        if getattr(collection, "db", None) is not None:
            collection.close()

    def bootstrap_upload(
        self, manifest: SyncManifest, manifest_dir: Path
    ) -> dict[str, Any]:
        """Create the first server collection, accepting only FULL_UPLOAD."""
        manifest.validate_media(manifest_dir)
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                initial = collection.sync_collection(auth, sync_media=False)
                if initial.required != initial.NO_CHANGES or not collection.is_empty():
                    raise SyncSafetyError(
                        "bootstrap-upload requires an empty local collection and empty server"
                    )
                create_notetype(collection, self.css)
                report = self._upsert(collection, manifest, manifest_dir)
                output = collection.sync_collection(auth, sync_media=False)
                if output.required != output.FULL_UPLOAD:
                    raise SyncSafetyError(
                        "bootstrap-upload expected Anki to require FULL_UPLOAD, got "
                        + _sync_requirement_name(output)
                    )
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=output.server_media_usn,
                    upload=True,
                )
                collection.reopen(after_full_sync=True)
                self._wait_for_media(collection)
                return {
                    "operation": "bootstrap-upload",
                    "sync": "full-upload-complete",
                    **report,
                }
            finally:
                self._close(collection)

    def adopt_server(self, *, confirm_no_other_clients: bool) -> dict[str, Any]:
        """Adopt a non-empty server and explicitly upload the new Acervo schema."""
        if not confirm_no_other_clients:
            raise SyncSafetyError(
                "adopt-server requires --confirm-no-other-clients"
            )
        if self.settings.collection_path.exists():
            raise SyncSafetyError(
                "adopt-server requires a new robot collection path; refusing to replace it"
            )
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                output = collection.sync_collection(auth, sync_media=False)
                if output.required != output.FULL_DOWNLOAD:
                    raise SyncSafetyError(
                        "adopt-server expected a non-empty server requiring FULL_DOWNLOAD, got "
                        + _sync_requirement_name(output)
                    )
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=output.server_media_usn,
                    upload=False,
                )
                collection.reopen(after_full_sync=True)
                self._wait_for_media(collection)
                self._backup(collection)
                create_notetype(collection, self.css)
                schema_output = collection.sync_collection(auth, sync_media=False)
                if schema_output.required not in (
                    schema_output.FULL_SYNC,
                    schema_output.FULL_UPLOAD,
                ):
                    raise SyncSafetyError(
                        "adopt-server expected a full upload choice after installing the "
                        f"Acervo note type, got {_sync_requirement_name(schema_output)}"
                    )
                collection.close_for_full_sync()
                collection.full_upload_or_download(
                    auth=auth,
                    server_usn=schema_output.server_media_usn,
                    upload=True,
                )
                collection.reopen(after_full_sync=True)
                self._wait_for_media(collection)
                return {
                    "operation": "adopt-server",
                    "sync": "full-download-and-schema-upload-complete",
                    "notes_preserved": collection.note_count(),
                }
            finally:
                self._close(collection)

    def push(self, manifest: SyncManifest, manifest_dir: Path) -> dict[str, Any]:
        """Sync down, update Acervo-owned notes, and sync up normally."""
        manifest.validate_media(manifest_dir)
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                self._normal_sync(collection, auth, stage="pre-mutation sync")
                require_notetype(collection, self.css)
                self._backup(collection)
                report = self._upsert(collection, manifest, manifest_dir)
                self._normal_sync(collection, auth, stage="post-mutation sync")
                return {"operation": "push", "sync": "complete", **report}
            finally:
                self._close(collection)

    def export_state(self) -> dict[str, Any]:
        """Sync down and export review state without mutating card content."""
        with self._exclusive_collection():
            collection = self._open_collection()
            try:
                auth = self._login(collection)
                self._normal_sync(collection, auth, stage="state-export sync")
                notetype = require_notetype(collection, self.css)
                notes = []
                for anki_note_id in collection.models.nids(notetype["id"]):
                    note = collection.get_note(anki_note_id)
                    cards = [self._card_state(collection, card) for card in note.cards()]
                    notes.append(
                        {
                            "note_id": note["AcervoNoteId"],
                            "lexeme_id": note["AcervoLexemeId"],
                            "anki_note_id": int(note.id),
                            "card_ids": [card["anki_card_id"] for card in cards],
                            "cards": cards,
                        }
                    )
                notes.sort(key=lambda item: item["note_id"])
                return {
                    "operation": "export-state",
                    "sync": "complete",
                    "notes": notes,
                }
            finally:
                self._close(collection)

    @staticmethod
    def _card_state(collection: Any, card: Any) -> dict[str, Any]:
        memory = card.memory_state
        stability = getattr(memory, "stability", None) if memory is not None else None
        difficulty = getattr(memory, "difficulty", None) if memory is not None else None
        if stability is None and card.reps:
            try:
                computed = collection.compute_memory_state(card.id)
                stability = computed.stability
                difficulty = computed.difficulty
            except Exception:
                pass
        last_review = (
            datetime.fromtimestamp(card.last_review_time, tz=UTC).isoformat()
            if card.last_review_time is not None
            else None
        )
        return {
            "anki_card_id": int(card.id),
            "reps": int(card.reps),
            "lapses": int(card.lapses),
            "queue": int(card.queue),
            "suspended": int(card.queue) == -1,
            "flag": int(card.user_flag()),
            "stability": stability,
            "difficulty": difficulty,
            "retrievability": None,
            "last_review": last_review,
        }

    def _upsert(
        self, collection: Any, manifest: SyncManifest, manifest_dir: Path
    ) -> dict[str, Any]:
        notetype = require_notetype(collection, self.css)
        existing: dict[str, Any] = {}
        for anki_note_id in collection.models.nids(notetype["id"]):
            note = collection.get_note(anki_note_id)
            identity = note["AcervoNoteId"]
            if identity in existing:
                raise DuplicateIdentityError(
                    f"AcervoNoteId {identity!r} occurs more than once in Anki"
                )
            existing[identity] = note

        selected: dict[str, Any | None] = {}
        for item in manifest.notes:
            identity = str(item.note_id)
            note_ids = collection.find_notes(f"AcervoNoteId:{identity}")
            if len(note_ids) > 1:
                raise DuplicateIdentityError(
                    f"AcervoNoteId {identity} occurs {len(note_ids)} times in Anki"
                )
            selected[identity] = collection.get_note(note_ids[0]) if note_ids else None

        created = updated = unchanged = media_added = 0
        results = []
        for item in manifest.notes:
            identity = str(item.note_id)
            note = selected[identity]
            is_new = note is None
            if is_new:
                note = collection.new_note(notetype)
            elif note.mid != notetype["id"]:
                raise DuplicateIdentityError(
                    f"AcervoNoteId {identity} belongs to an unexpected note type"
                )

            comment, added = self._render_comment(collection, item, manifest_dir)
            media_added += added
            fields = {
                "AcervoNoteId": identity,
                "AcervoLexemeId": str(item.lexeme_id),
                "Sentence": item.sentence,
                "Translation": item.translation,
                "Comment": comment,
            }
            managed_tags = set(item.tags)
            preserved_tags = {
                tag for tag in note.tags if not tag.casefold().startswith("acervo::")
            }
            desired_tags = sorted(preserved_tags | managed_tags)
            deck_id = collection.decks.id(item.deck)
            changed = is_new or any(note[name] != value for name, value in fields.items())
            changed = changed or sorted(note.tags) != desired_tags
            card_ids_before = [int(card_id) for card_id in note.card_ids()] if not is_new else []
            deck_changed = False
            if not is_new:
                deck_changed = any(card.did != deck_id for card in note.cards())
                changed = changed or deck_changed

            for name, value in fields.items():
                note[name] = value
            note.tags = desired_tags
            if is_new:
                collection.add_note(note, deck_id)
                created += 1
            elif changed:
                collection.update_note(note)
                if deck_changed:
                    collection.set_deck(note.card_ids(), deck_id)
                updated += 1
            else:
                unchanged += 1
            results.append(
                {
                    "note_id": identity,
                    "anki_note_id": int(note.id),
                    "card_ids": [int(card_id) for card_id in note.card_ids()],
                    "previous_card_ids": card_ids_before,
                    "status": "created" if is_new else ("updated" if changed else "unchanged"),
                }
            )
        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "media_added": media_added,
            "notes": results,
        }

    @staticmethod
    def _render_comment(
        collection: Any, item: SyncManifestNote, manifest_dir: Path
    ) -> tuple[str, int]:
        blocks: list[str] = []
        added = 0
        for kind in ("image", "audio"):
            source = item.media_source(kind, manifest_dir)
            if source is None:
                continue
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:20]
            suffix = source.suffix.lower()
            stem = slugify_filename(source.stem) or kind
            desired_name = f"acervo-{digest}-{stem}{suffix}"
            existed = collection.media.have(desired_name)
            actual_name = collection.media.write_data(desired_name, data)
            if actual_name != desired_name:
                raise RuntimeError(
                    f"Unexpected Anki media collision: {desired_name} became {actual_name}"
                )
            added += not existed
            escaped = html.escape(actual_name, quote=True)
            if kind == "image":
                blocks.append(f'<div class="image"><img src="{escaped}"></div>')
            else:
                blocks.append(
                    f'<div class="audio">[sound:{actual_name}] Listen to pronunciation</div>'
                )
        if item.comment_html:
            blocks.append(item.comment_html)
        return "\n".join(blocks), added


def result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)

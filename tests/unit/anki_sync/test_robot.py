import fcntl
from pathlib import Path

import pytest
from anki.collection import Collection

from vocabgen.anki_sync.manifest import SyncManifest
from vocabgen.anki_sync.model import create_notetype
from vocabgen.anki_sync.robot import (
    AnkiRobot,
    DuplicateIdentityError,
    RobotSettings,
    SyncSafetyError,
)


NOTE_ID = "note00000000001"
LEXEME_ID = "lexeme000000001"


def make_robot(tmp_path: Path) -> AnkiRobot:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "anki.css").write_text(".card {}", encoding="utf-8")
    (tmp_path / "robot").mkdir()
    return AnkiRobot(
        RobotSettings(
            endpoint="http://example.invalid/",
            username="user",
            password="password",
            collection_path=tmp_path / "robot" / "collection.anki2",
            backup_dir=tmp_path / "backups",
            template_dir=template_dir,
        )
    )


def manifest(**overrides) -> SyncManifest:
    item = {
        "note_id": NOTE_ID,
        "lexeme_id": LEXEME_ID,
        "deck": "Spanish::Vocabulary",
        "sentence": "La balsa",
        "translation": "The raft",
        "comment_html": "<p>v1</p>",
        "tags": ["acervo::topic::travel"],
    }
    item.update(overrides)
    return SyncManifest.model_validate({"schema_version": 1, "notes": [item]})


def test_upsert_creates_updates_and_then_becomes_noop(tmp_path):
    robot = make_robot(tmp_path)
    collection = Collection(str(robot.settings.collection_path))
    try:
        create_notetype(collection, robot.css)
        first = robot._upsert(collection, manifest(), tmp_path)
        note_id = first["notes"][0]["anki_note_id"]
        card_ids = first["notes"][0]["card_ids"]
        note = collection.get_note(note_id)
        note.add_tag("marked")
        collection.update_note(note)
        card = note.cards()[0]
        card.reps = 7
        card.lapses = 2
        collection.update_card(card)

        second = robot._upsert(
            collection,
            manifest(sentence="La balsa actualizada", tags=["acervo::topic::nature"]),
            tmp_path,
        )
        third = robot._upsert(
            collection,
            manifest(sentence="La balsa actualizada", tags=["acervo::topic::nature"]),
            tmp_path,
        )

        updated = collection.get_note(note_id)
        assert first["created"] == 1
        assert second["updated"] == 1
        assert third["unchanged"] == 1
        assert [int(value) for value in updated.card_ids()] == card_ids
        assert updated["Sentence"] == "La balsa actualizada"
        assert set(updated.tags) == {"marked", "acervo::topic::nature"}
        assert updated.cards()[0].reps == 7
        assert updated.cards()[0].lapses == 2
    finally:
        collection.close()


def test_upsert_moves_existing_card_without_recreating_it(tmp_path):
    robot = make_robot(tmp_path)
    collection = Collection(str(robot.settings.collection_path))
    try:
        create_notetype(collection, robot.css)
        first = robot._upsert(collection, manifest(), tmp_path)
        card_id = first["notes"][0]["card_ids"][0]
        robot._upsert(collection, manifest(deck="Spanish::Updated"), tmp_path)
        card = collection.get_card(card_id)
        assert card.did == collection.decks.id("Spanish::Updated", create=False)
    finally:
        collection.close()


def test_upsert_imports_content_addressed_media(tmp_path):
    robot = make_robot(tmp_path)
    (tmp_path / "picture.webp").write_bytes(b"picture")
    (tmp_path / "voice.mp3").write_bytes(b"voice")
    collection = Collection(str(robot.settings.collection_path))
    try:
        create_notetype(collection, robot.css)
        report = robot._upsert(
            collection,
            manifest(image_path="picture.webp", audio_path="voice.mp3"),
            tmp_path,
        )
        note = collection.get_note(report["notes"][0]["anki_note_id"])
        assert report["media_added"] == 2
        assert '<img src="acervo-' in note["Comment"]
        assert "[sound:acervo-" in note["Comment"]
        assert robot._upsert(
            collection,
            manifest(image_path="picture.webp", audio_path="voice.mp3"),
            tmp_path,
        )["media_added"] == 0
    finally:
        collection.close()


def test_upsert_refuses_duplicate_collection_identity(tmp_path):
    robot = make_robot(tmp_path)
    collection = Collection(str(robot.settings.collection_path))
    try:
        notetype = create_notetype(collection, robot.css)
        for sentence in ("one", "two"):
            note = collection.new_note(notetype)
            note["AcervoNoteId"] = NOTE_ID
            note["AcervoLexemeId"] = LEXEME_ID
            note["Sentence"] = sentence
            note["Translation"] = sentence
            collection.add_note(note, collection.decks.id("Spanish"))
        with pytest.raises(DuplicateIdentityError, match="occurs"):
            robot._upsert(collection, manifest(), tmp_path)
    finally:
        collection.close()


def test_upsert_refuses_unrelated_duplicate_collection_identity(tmp_path):
    robot = make_robot(tmp_path)
    collection = Collection(str(robot.settings.collection_path))
    try:
        notetype = create_notetype(collection, robot.css)
        for sentence in ("one", "two"):
            note = collection.new_note(notetype)
            note["AcervoNoteId"] = "note00000000003"
            note["AcervoLexemeId"] = LEXEME_ID
            note["Sentence"] = sentence
            note["Translation"] = sentence
            collection.add_note(note, collection.decks.id("Spanish"))
        with pytest.raises(DuplicateIdentityError, match="occurs"):
            robot._upsert(collection, manifest(), tmp_path)
    finally:
        collection.close()


def test_card_state_exports_review_and_flag_values(tmp_path):
    robot = make_robot(tmp_path)
    collection = Collection(str(robot.settings.collection_path))
    try:
        notetype = create_notetype(collection, robot.css)
        note = collection.new_note(notetype)
        note["AcervoNoteId"] = NOTE_ID
        note["AcervoLexemeId"] = LEXEME_ID
        note["Sentence"] = "one"
        note["Translation"] = "one"
        collection.add_note(note, collection.decks.id("Spanish"))
        card = note.cards()[0]
        card.reps = 4
        card.lapses = 1
        card.flags = 3
        collection.update_card(card)
        state = robot._card_state(collection, collection.get_card(card.id))
        assert state["reps"] == 4
        assert state["lapses"] == 1
        assert state["flag"] == 3
        assert state["retrievability"] is None
    finally:
        collection.close()


def test_robot_collection_lock_refuses_concurrent_process(tmp_path):
    robot = make_robot(tmp_path)
    lock_path = robot.settings.collection_path.parent / ".acervo-anki-robot.lock"
    with lock_path.open("a+", encoding="utf-8") as held_lock:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SyncSafetyError, match="already running"):
            with robot._exclusive_collection():
                pass

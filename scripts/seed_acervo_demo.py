#!/usr/bin/env python3
"""Insert disposable demonstration vocabulary into one existing Acervo account."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


STAMP = "2026-08-28T12:00:00.000Z"
EDITOR = "acervoseed"


def record_id(owner_id: str, collection: str, key: str) -> str:
    """Return a stable owner-scoped id in PocketBase's native record-id format."""
    return hashlib.sha256(f"{owner_id}:{collection}:{key}".encode()).hexdigest()[:15]


class PocketBaseError(RuntimeError):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class PocketBase:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, data: dict | None = None) -> dict:
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = self.token
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
                message = payload.get("message") or payload.get("error", {}).get("message")
            except Exception:
                message = None
            raise PocketBaseError(
                message or f"PocketBase returned HTTP {error.code}.",
                error.code,
            ) from error

    def exists(self, collection: str, identifier: str) -> bool:
        try:
            self.request("GET", f"/api/collections/{collection}/records/{identifier}")
            return True
        except PocketBaseError as error:
            if error.status == 404:
                return False
            raise

    def create(self, collection: str, record: dict) -> bool:
        if self.exists(collection, record["id"]):
            return False
        self.request("POST", f"/api/collections/{collection}/records", record)
        return True


def sync_fields() -> dict:
    return {
        "deleted": False,
        "created_at": STAMP,
        "edited_at": STAMP,
        "edited_by": EDITOR,
        "revision": 0,
    }


def demo_records(owner_id: str) -> list[tuple[str, dict]]:
    rid = lambda collection, key: record_id(owner_id, collection, key)
    lexemes = {
        "balsa": rid("lexemes", "balsa"),
        "desmayarse": rid("lexemes", "desmayarse"),
        "mejoren": rid("lexemes", "que-se-mejoren"),
        "turmoil": rid("lexemes", "turmoil"),
        "library": rid("lexemes", "library-zh"),
    }
    base = {"owner": owner_id, **sync_fields()}
    records: list[tuple[str, dict]] = []

    def lexeme(key: str, **fields: object) -> None:
        records.append(("lexemes", {"id": lexemes[key], **base, **fields}))

    lexeme("balsa", language="es", headword="la balsa", lemma="balsa", reading="", pos="noun",
           gender="feminine", register="neutral", dialect="", emoji="🛶", topics=["travel", "nature"],
           status="active", short_gloss="", notes=[])
    lexeme("desmayarse", language="es", headword="desmayarse", lemma="desmayarse", reading="", pos="verb",
           gender="", register="neutral", dialect="", emoji="😵‍💫", topics=["health"], status="active",
           short_gloss="", notes=["Pronominal verb."])
    lexeme("mejoren", language="es", headword="que se mejoren", lemma="que se mejoren", reading="", pos="expression",
           gender="", register="neutral", dialect="", emoji="💖", topics=["health", "social"], status="active",
           short_gloss="", notes=[])
    lexeme("turmoil", language="en", headword="turmoil", lemma="turmoil", reading="", pos="noun",
           gender="", register="neutral", dialect="", emoji="🌪️", topics=["emotions"], status="active",
           short_gloss="", notes=[])
    lexeme("library", language="zh-Hans", headword="图书馆", lemma="图书馆", reading="tu2 shu1 guan3", pos="noun",
           gender="", register="neutral", dialect="", emoji="📚", topics=["places"], status="active",
           short_gloss="", notes=[])

    senses = {
        "balsa": rid("senses", "balsa-0"),
        "faint": rid("senses", "desmayarse-0"),
        "emotion": rid("senses", "desmayarse-1"),
        "mejoren": rid("senses", "mejoren-0"),
        "turmoil": rid("senses", "turmoil-0"),
        "library": rid("senses", "library-0"),
    }

    def sense(key: str, lexeme_key: str, definition: str, definition_lang: str, glosses: list[dict], order: int, domain: str = "") -> None:
        records.append(("senses", {
            "id": senses[key], **base, "lexeme": lexemes[lexeme_key], "definition": definition,
            "definition_lang": definition_lang, "glosses": glosses, "domain": domain, "sense_order": order,
        }))

    sense("balsa", "balsa", "Plataforma flotante sencilla que se usa como embarcación.", "es", [{"lang": "en", "terms": ["raft"]}], 0)
    sense("faint", "desmayarse", "Perder brevemente el conocimiento.", "es", [{"lang": "en", "terms": ["to faint", "to pass out"]}], 0, "health")
    sense("emotion", "desmayarse", "Sentirse abrumado por una emoción intensa.", "es", [{"lang": "en", "terms": ["to be overcome"]}], 1)
    sense("mejoren", "mejoren", "Fórmula para desear a alguien una pronta recuperación.", "es", [
        {"lang": "en", "terms": ["get better", "feel better soon"]},
        {"lang": "ru", "terms": ["выздоравливайте"]},
    ], 0, "health")
    sense("turmoil", "turmoil", "A state of great confusion, disturbance or uncertainty.", "en", [
        {"lang": "ru", "terms": ["суматоха", "смятение", "потрясения"]},
    ], 0)
    sense("library", "library", "收藏和提供书籍供人阅读或借阅的场所。", "zh-Hans", [
        {"lang": "en", "terms": ["library"]}, {"lang": "ru", "terms": ["библиотека"]},
    ], 0, "places")

    attestations = {
        "faint": rid("attestations", "faint-lesson"),
        "turmoil": rid("attestations", "turmoil-book"),
    }
    records.extend([
        ("attestations", {"id": attestations["faint"], **base, "lexeme": lexemes["desmayarse"],
         "text": "se desmayo durante la clase", "translation": "", "source_url": "https://example.com/lesson",
         "source_title": "Language lesson", "source_kind": "lesson", "captured_at": STAMP}),
        ("attestations", {"id": attestations["turmoil"], **base, "lexeme": lexemes["turmoil"],
         "text": "The sudden change left the town in turmoil.", "translation": "",
         "source_title": "Example reader", "source_kind": "book", "captured_at": STAMP}),
    ])

    def example(key: str, sense_key: str, text: str, text_lang: str, translation: str, translation_lang: str,
                origin: str = "manual", source: str = "", model: str = "") -> None:
        records.append(("examples", {
            "id": rid("examples", key), **base, "sense": senses[sense_key], "text": text, "text_lang": text_lang,
            "translation": translation, "translation_lang": translation_lang, "origin": origin,
            "source_attestation": source, "model_id": model, "video_ref": "", "image_ref": "", "audio_ref": "",
            "note": "", "approved": True,
        }))

    example("balsa", "balsa", "Cruzaron el río en una balsa.", "es", "They crossed the river on a raft.", "en")
    example("faint", "faint", "Se desmayó durante la clase.", "es", "They fainted during class.", "en", "attestation", attestations["faint"], "demo-cleaner")
    example("emotion", "emotion", "Casi me desmayo de la emoción.", "es", "I nearly fainted from excitement.", "en")
    example("mejoren", "mejoren", "Espero que se mejoren pronto.", "es", "I hope you feel better soon.", "en")
    example("turmoil", "turmoil", "The sudden change left the town in turmoil.", "en", "Внезапная перемена привела город в смятение.", "ru", "attestation", attestations["turmoil"])
    example("library", "library", "我在图书馆看书。", "zh-Hans", "I read at the library.", "en")

    records.extend([
        ("image_prompts", {"id": rid("image_prompts", "balsa"), **base, "lexeme": lexemes["balsa"], "sense": "",
         "prompt": "A small wooden raft floating on a calm river, no text.", "style_id": "study-card",
         "seed": 184521, "model_id": "demo-prompt", "prompt_version": "demo-v1"}),
        ("image_prompts", {"id": rid("image_prompts", "faint"), **base, "lexeme": lexemes["desmayarse"], "sense": senses["faint"],
         "prompt": "A safe classroom scene suggesting a person briefly fainted, no text.", "style_id": "study-card",
         "seed": 991204, "model_id": "demo-prompt", "prompt_version": "demo-v1"}),
        ("study_states", {"id": rid("study_states", "desmayarse-anki"), **base, "lexeme": lexemes["desmayarse"],
         "system": "anki", "note_id": 1738291045123, "card_ids": [1738291045124], "reps": 14, "lapses": 3,
         "stability": 41.7, "difficulty": 7.9, "retrievability": 0.86, "last_review": STAMP, "synced_at": STAMP}),
    ])
    return records


def normalize_server_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip().rstrip("/"))
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Use HTTPS, except for a local PocketBase instance.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Provide only the PocketBase server base URL.")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--owner-email", required=True, help="Existing Acervo user that will own the demo records")
    parser.add_argument("--superuser-email", default=os.getenv("ACERVO_PB_SUPERUSER_EMAIL", ""))
    args = parser.parse_args()
    server = normalize_server_url(args.server_url)
    admin_email = args.superuser_email.strip() or input("PocketBase superuser email: ").strip()
    admin_password = os.getenv("ACERVO_PB_SUPERUSER_PASSWORD") or getpass.getpass("PocketBase superuser password: ")

    client = PocketBase(server)
    auth = client.request("POST", "/api/collections/_superusers/auth-with-password", {
        "identity": admin_email, "password": admin_password,
    })
    client.token = auth["token"]
    owner_filter = urllib.parse.quote(f'email="{args.owner_email.strip()}"')
    owners = client.request("GET", f"/api/collections/users/records?perPage=2&filter={owner_filter}").get("items", [])
    if len(owners) != 1:
        raise RuntimeError("The owner email must identify exactly one existing Acervo account.")

    created = 0
    skipped = 0
    for collection, record in demo_records(owners[0]["id"]):
        if client.create(collection, record):
            created += 1
        else:
            skipped += 1
    print(f"Acervo demo data ready for {args.owner_email.strip()}: created {created}, already present {skipped}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)

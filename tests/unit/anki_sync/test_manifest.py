import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from vocabgen.anki_sync.manifest import SyncManifest


NOTE_ID = "22222222-2222-4222-8222-222222222222"
LEXEME_ID = "11111111-1111-4111-8111-111111111111"


def payload(**note_overrides):
    note = {
        "note_id": NOTE_ID,
        "lexeme_id": LEXEME_ID,
        "deck": "Spanish::Vocabulary",
        "sentence": "La balsa",
        "translation": "The raft",
        "comment_html": "<p>A sample.</p>",
        "tags": ["acervo::topic::travel"],
    }
    note.update(note_overrides)
    return {"schema_version": 1, "notes": [note]}


def test_manifest_accepts_the_versioned_contract():
    manifest = SyncManifest.model_validate(payload())
    assert str(manifest.notes[0].note_id) == NOTE_ID


@pytest.mark.parametrize(
    "change,match",
    [
        ({"schema_version": 2}, "schema_version"),
        ({"tags": ["travel"]}, "acervo::"),
        ({"tags": ["acervo::x", "acervo::x"]}, "unique"),
    ],
)
def test_manifest_rejects_unsupported_or_unmanaged_values(change, match):
    value = payload()
    if "schema_version" in change:
        value.update(change)
    else:
        value["notes"][0].update(change)
    with pytest.raises(ValidationError, match=match):
        SyncManifest.model_validate(value)


def test_manifest_rejects_duplicate_note_ids():
    value = payload()
    value["notes"].append(dict(value["notes"][0]))
    with pytest.raises(ValidationError, match="note_id values must be unique"):
        SyncManifest.model_validate(value)


def test_manifest_resolves_media_only_inside_its_directory(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "image.webp").write_bytes(b"image")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(payload(image_path="media/image.webp")), encoding="utf-8"
    )

    manifest, root = SyncManifest.load(manifest_path)
    assert manifest.notes[0].media_source("image", root) == media / "image.webp"


@pytest.mark.parametrize("unsafe", ["../outside.webp", "/tmp/outside.webp"])
def test_manifest_rejects_media_path_escape(tmp_path, unsafe):
    manifest = SyncManifest.model_validate(payload(image_path=unsafe))
    with pytest.raises((ValueError, FileNotFoundError), match="relative|escapes"):
        manifest.validate_media(tmp_path)

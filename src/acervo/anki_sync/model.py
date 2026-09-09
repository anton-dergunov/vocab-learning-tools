from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


MODEL_NAME = "Acervo Vocabulary"
MODEL_VERSION = 1
FIELD_NAMES = (
    "AcervoNoteId",
    "AcervoLexemeId",
    "Sentence",
    "Translation",
    "Comment",
)
TEMPLATE_NAME = "Recognition"
QUESTION_FORMAT = '<div class="phrase">{{Sentence}}</div>'
ANSWER_FORMAT = (
    '{{FrontSide}}<hr id="answer">'
    '<div class="translation">{{Translation}}</div>{{Comment}}'
)


class ModelMismatchError(RuntimeError):
    """The collection has an incompatible Acervo-owned note type."""


def load_css(template_dir: str | Path) -> str:
    return (Path(template_dir) / "anki.css").read_text(encoding="utf-8")


def expected_signature(css: str) -> str:
    payload = {
        "version": MODEL_VERSION,
        "fields": FIELD_NAMES,
        "template": {
            "name": TEMPLATE_NAME,
            "qfmt": QUESTION_FORMAT,
            "afmt": ANSWER_FORMAT,
        },
        "css": css,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def actual_signature(notetype: dict[str, Any]) -> str:
    templates = notetype.get("tmpls", [])
    template = templates[0] if len(templates) == 1 else {}
    payload = {
        "version": MODEL_VERSION,
        "fields": tuple(field.get("name") for field in notetype.get("flds", [])),
        "template": {
            "name": template.get("name"),
            "qfmt": template.get("qfmt"),
            "afmt": template.get("afmt"),
        },
        "css": notetype.get("css", ""),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def require_notetype(collection: Any, css: str) -> dict[str, Any]:
    notetype = collection.models.by_name(MODEL_NAME)
    if notetype is None:
        raise ModelMismatchError(
            "The Acervo note type is missing; run bootstrap-upload or adopt-server first"
        )
    if actual_signature(notetype) != expected_signature(css):
        raise ModelMismatchError(
            "The Acervo note type schema/template differs from this robot version; "
            "routine synchronization will not modify it"
        )
    return notetype


def create_notetype(collection: Any, css: str) -> dict[str, Any]:
    if collection.models.by_name(MODEL_NAME) is not None:
        raise ModelMismatchError(f"The {MODEL_NAME!r} note type already exists")
    notetype = collection.models.new(MODEL_NAME)
    for name in FIELD_NAMES:
        collection.models.add_field(notetype, collection.models.new_field(name))
    collection.models.set_sort_index(notetype, FIELD_NAMES.index("Sentence"))
    template = collection.models.new_template(TEMPLATE_NAME)
    template["qfmt"] = QUESTION_FORMAT
    template["afmt"] = ANSWER_FORMAT
    collection.models.add_template(notetype, template)
    notetype["css"] = css
    collection.models.add(notetype)
    return require_notetype(collection, css)

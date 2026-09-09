"""Storage <-> client mapping, in graph order.

Maps the snake_case storage boundary onto the camelCase client model in `web/src/domain.ts`.
Tombstones are included; the client owns filtering.

The order of `COLLECTIONS` is load-bearing three times over. It is the order a pull is assembled in;
it is the merge order the write route applies a batch in, so a relation always resolves before the
record that names it; and reversed, with the first two entries dropped, it is the tombstone order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Table

from acervo.db import tables

# ── coercion ────────────────────────────────────────────────────────────────
# The client is not the only writer and a model's answer reaches `assign` too, so every one of these
# is deliberately total: it produces a storable value for anything, and validation — not coercion —
# is what refuses a record.


def trimmed(value: Any) -> str:
    return "" if value is None else str(value).strip()


def text_or_none(value: Any) -> str | None:
    """What the wire calls an absent string. Storage keeps `""`; the projection says `null`."""
    return trimmed(value) or None


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def to_bool(value: Any) -> bool:
    return value is True


@dataclass(frozen=True)
class Collection:
    """One row of the projection table: a wire key, a storage table, and the two directions."""

    key: str
    table: Table
    project: Callable[[Mapping[str, Any]], dict[str, Any]]
    assign: Callable[[Mapping[str, Any]], dict[str, Any]]

    @property
    def name(self) -> str:
        return self.table.name


def _project_vocabulary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "definitionLang": row["definition_lang"],
        "glossLangs": to_list(row["gloss_langs"]),
        "notesLang": row["notes_lang"],
        "displayName": text_or_none(row["display_name"]),
        "flag": text_or_none(row["flag"]),
        "order": to_int(row["vocab_order"]),
    }


def _assign_vocabulary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "definition_lang": trimmed(value.get("definitionLang")),
        "gloss_langs": to_list(value.get("glossLangs")),
        "notes_lang": trimmed(value.get("notesLang")),
        "display_name": trimmed(value.get("displayName")),
        "flag": trimmed(value.get("flag")),
        "vocab_order": to_int(value.get("order")),
    }


def _project_topic(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "icon": text_or_none(row["icon"]),
        "order": to_int(row["topic_order"]),
    }


def _assign_topic(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": trimmed(value.get("name")),
        "icon": trimmed(value.get("icon")),
        "topic_order": to_int(value.get("order")),
    }


def _project_lexeme(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": row["language"],
        "headword": row["headword"],
        "lemma": row["lemma"],
        "reading": text_or_none(row["reading"]),
        "ipa": text_or_none(row["ipa"]),
        "pos": row["pos"],
        "gender": text_or_none(row["gender"]),
        "register": text_or_none(row["register"]),
        "dialect": text_or_none(row["dialect"]),
        "emoji": text_or_none(row["emoji"]),
        "topicIds": to_list(row["topics"]),
        "status": row["status"],
        "shortGloss": text_or_none(row["short_gloss"]),
        "notes": to_list(row["notes"]),
    }


def _assign_lexeme(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "language": trimmed(value.get("language")),
        "headword": trimmed(value.get("headword")),
        "lemma": trimmed(value.get("lemma")),
        "reading": trimmed(value.get("reading")),
        "ipa": trimmed(value.get("ipa")),
        "pos": trimmed(value.get("pos")),
        "gender": trimmed(value.get("gender")),
        "register": trimmed(value.get("register")),
        "dialect": trimmed(value.get("dialect")),
        "emoji": trimmed(value.get("emoji")),
        "topics": to_list(value.get("topicIds")),
        "status": trimmed(value.get("status")),
        "short_gloss": trimmed(value.get("shortGloss")),
        "notes": to_list(value.get("notes")),
    }


def _project_sense(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "definition": row["definition"],
        "definitionLang": row["definition_lang"],
        "glosses": to_list(row["glosses"]),
        "domain": text_or_none(row["domain"]),
        "order": to_int(row["sense_order"]),
    }


def _assign_sense(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "definition": trimmed(value.get("definition")),
        "definition_lang": trimmed(value.get("definitionLang")),
        "glosses": to_list(value.get("glosses")),
        "domain": trimmed(value.get("domain")),
        "sense_order": to_int(value.get("order")),
    }


def _project_attestation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "text": row["text"],
        "translation": text_or_none(row["translation"]),
        "sourceUrl": text_or_none(row["source_url"]),
        "sourceTitle": text_or_none(row["source_title"]),
        "sourceKind": row["source_kind"],
        "capturedAt": text_or_none(row["captured_at"]),
    }


def _assign_attestation(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "text": trimmed(value.get("text")),
        "translation": trimmed(value.get("translation")),
        "source_url": trimmed(value.get("sourceUrl")),
        "source_title": trimmed(value.get("sourceTitle")),
        "source_kind": trimmed(value.get("sourceKind")),
        "captured_at": trimmed(value.get("capturedAt")),
    }


def _project_example(row: Mapping[str, Any]) -> dict[str, Any]:
    # A clip title and a start time are hidden when there is no reference. That invariant is asserted
    # twice on purpose — the validator refuses the combination on the way in, and this refuses to
    # show it on the way out.
    video_ref = text_or_none(row["video_ref"])
    return {
        "senseId": row["sense"],
        "text": row["text"],
        "textLang": row["text_lang"],
        "translation": text_or_none(row["translation"]),
        "translationLang": text_or_none(row["translation_lang"]),
        "origin": row["origin"],
        "sourceAttestationId": text_or_none(row["source_attestation"]),
        "modelId": text_or_none(row["model_id"]),
        "videoRef": video_ref,
        "videoTitle": text_or_none(row["video_title"]) if video_ref else None,
        "videoStart": to_int(row["video_start"]) if video_ref else None,
        "imageRef": text_or_none(row["image_ref"]),
        "audioRef": text_or_none(row["audio_ref"]),
        "note": text_or_none(row["note"]),
        "matchedForm": text_or_none(row["matched_form"]),
        "matchedTranslationForm": text_or_none(row["matched_translation_form"]),
        "approved": bool(row["approved"]),
    }


def _assign_example(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sense": trimmed(value.get("senseId")),
        "text": trimmed(value.get("text")),
        "text_lang": trimmed(value.get("textLang")),
        "translation": trimmed(value.get("translation")),
        "translation_lang": trimmed(value.get("translationLang")),
        "origin": trimmed(value.get("origin")),
        # A relation, so an absent one is NULL rather than "": a foreign key of "" resolves to
        # nothing and would trip the constraint.
        "source_attestation": trimmed(value.get("sourceAttestationId")) or None,
        "model_id": trimmed(value.get("modelId")),
        "video_ref": trimmed(value.get("videoRef")),
        "video_title": trimmed(value.get("videoTitle")),
        "video_start": to_int(value.get("videoStart")),
        "image_ref": trimmed(value.get("imageRef")),
        "audio_ref": trimmed(value.get("audioRef")),
        "note": trimmed(value.get("note")),
        "matched_form": trimmed(value.get("matchedForm")),
        "matched_translation_form": trimmed(value.get("matchedTranslationForm")),
        "approved": to_bool(value.get("approved")),
    }


def _project_image_prompt(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "senseId": text_or_none(row["sense"]),
        "prompt": row["prompt"],
        "styleId": row["style_id"],
        "seed": to_int(row["seed"]),
        "modelId": row["model_id"],
        "promptVersion": row["prompt_version"],
        "imageRef": text_or_none(row["image_ref"]),
        "imageModelId": text_or_none(row["image_model_id"]),
    }


def _assign_image_prompt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "sense": trimmed(value.get("senseId")) or None,
        "prompt": trimmed(value.get("prompt")),
        "style_id": trimmed(value.get("styleId")),
        "seed": to_int(value.get("seed")),
        "model_id": trimmed(value.get("modelId")),
        "prompt_version": trimmed(value.get("promptVersion")),
        "image_ref": trimmed(value.get("imageRef")),
        "image_model_id": trimmed(value.get("imageModelId")),
    }


def _project_study_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexemeId": row["lexeme"],
        "system": row["system"],
        # Alone among the numbers, zero projects as null: there is no Anki note 0, so a stored zero
        # means "not pushed yet" rather than "note zero".
        "noteId": to_int(row["note_id"]) or None,
        "cardIds": to_list(row["card_ids"]),
        "reps": to_int(row["reps"]),
        "lapses": to_int(row["lapses"]),
        "stability": to_float(row["stability"]),
        "difficulty": to_float(row["difficulty"]),
        "retrievability": to_float(row["retrievability"]),
        "lastReview": text_or_none(row["last_review"]),
        "syncedAt": text_or_none(row["synced_at"]),
    }


def _assign_study_state(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lexeme": trimmed(value.get("lexemeId")),
        "system": trimmed(value.get("system")),
        "note_id": to_int(value.get("noteId")),
        "card_ids": to_list(value.get("cardIds")),
        "reps": to_int(value.get("reps")),
        "lapses": to_int(value.get("lapses")),
        "stability": to_float(value.get("stability")),
        "difficulty": to_float(value.get("difficulty")),
        "retrievability": to_float(value.get("retrievability")),
        "last_review": trimmed(value.get("lastReview")),
        "synced_at": trimmed(value.get("syncedAt")),
    }


COLLECTIONS: tuple[Collection, ...] = (
    Collection("vocabularies", tables.vocabularies, _project_vocabulary, _assign_vocabulary),
    Collection("topics", tables.topics, _project_topic, _assign_topic),
    Collection("lexemes", tables.lexemes, _project_lexeme, _assign_lexeme),
    Collection("senses", tables.senses, _project_sense, _assign_sense),
    Collection("attestations", tables.attestations, _project_attestation, _assign_attestation),
    Collection("examples", tables.examples, _project_example, _assign_example),
    Collection("imagePrompts", tables.image_prompts, _project_image_prompt, _assign_image_prompt),
    Collection("studyStates", tables.study_states, _project_study_state, _assign_study_state),
)

COLLECTION_BY_KEY = {collection.key: collection for collection in COLLECTIONS}
COLLECTION_BY_NAME = {collection.name: collection for collection in COLLECTIONS}

# Every word and its descendants, newest relation first. Vocabularies and topics are excluded: a
# reset discards the words, not the languages the owner studies or the topics they file them under.
WORD_COLLECTIONS: tuple[Collection, ...] = tuple(reversed(COLLECTIONS[2:]))


def sync_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ownerId": row["owner"],
        "deleted": bool(row["deleted"]),
        "createdAt": row["created_at"],
        "editedAt": row["edited_at"],
        "editedBy": row["edited_by"],
        "revision": to_int(row["revision"]),
    }


def projected(collection: Collection, row: Mapping[str, Any]) -> dict[str, Any]:
    value = collection.project(row)
    value["id"] = row["id"]
    value.update(sync_fields(row))
    return value

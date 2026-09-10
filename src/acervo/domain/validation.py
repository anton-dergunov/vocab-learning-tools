"""The rules every write is held to, whichever writer it came from.

Ported from the PocketBase record-validation hook plus the field constraints its migration declared,
which SQLite does not enforce for us: a `select` was a real storage constraint and a `max` was a real
length bound, so both are checks here.

Each rule below has a test today and each is something a reasonable re-derivation gets subtly wrong.
The comments mark the ones where that is most true.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from acervo.domain.ids import is_instant, is_language, is_record_id
from acervo.errors import RecordRefused

POS_VALUES = ("noun", "verb", "adj", "adv", "phrase", "idiom", "expression")
GENDER_VALUES = ("masculine", "feminine", "common", "neuter")
REGISTER_VALUES = ("neutral", "formal", "colloquial", "slang", "vulgar")
STATUS_VALUES = ("inbox", "active", "learned", "retired", "suppressed")
SOURCE_KIND_VALUES = ("web", "book", "conversation", "video", "lesson", "unknown")
ORIGIN_VALUES = ("attestation", "llm", "tatoeba", "subtitle", "wiktionary", "manual")

# field -> (required, maximum length). Straight from the bootstrap migration.
TEXT_RULES: dict[str, dict[str, tuple[bool, int]]] = {
    "vocabularies": {
        "language": (True, 35), "definition_lang": (True, 35), "notes_lang": (True, 35),
        "display_name": (False, 120), "flag": (False, 32),
    },
    "topics": {"name": (True, 120), "icon": (False, 120)},
    "lexemes": {
        "language": (True, 35), "headword": (True, 240), "lemma": (True, 240),
        "reading": (False, 240), "ipa": (False, 240), "dialect": (False, 35),
        "emoji": (False, 32), "short_gloss": (False, 500),
    },
    "senses": {
        "definition": (True, 2000), "definition_lang": (True, 35), "domain": (False, 120),
    },
    "attestations": {
        "text": (True, 5000), "translation": (False, 5000), "source_title": (False, 500),
    },
    "examples": {
        "text": (True, 5000), "text_lang": (True, 35), "translation": (False, 5000),
        "translation_lang": (False, 35), "model_id": (False, 240), "video_ref": (False, 500),
        "video_title": (False, 500), "image_ref": (False, 500), "audio_ref": (False, 500),
        "note": (False, 2000), "matched_form": (False, 240),
        "matched_translation_form": (False, 240),
    },
    "image_prompts": {
        # `prompt` is optional because two legitimate rows have none: one the writer refused, which
        # is a finished outcome recorded so nothing asks again, and one holding a picture the owner
        # supplied themselves, which no brief produced.
        "prompt": (False, 10000), "style_id": (False, 120), "model_id": (False, 240),
        "prompt_version": (False, 128), "image_ref": (False, 500), "image_model_id": (False, 240),
        "failure_reason": (False, 500),
    },
    "study_states": {"system": (True, 80)},
}

SELECT_RULES: dict[str, dict[str, tuple[tuple[str, ...], bool]]] = {
    "lexemes": {
        "pos": (POS_VALUES, True),
        "gender": (GENDER_VALUES, False),
        "register": (REGISTER_VALUES, False),
        "status": (STATUS_VALUES, True),
    },
    "attestations": {"source_kind": (SOURCE_KIND_VALUES, True)},
    "examples": {"origin": (ORIGIN_VALUES, True)},
}

# field -> (minimum, maximum or None)
NUMBER_RULES: dict[str, dict[str, tuple[float, float | None]]] = {
    "vocabularies": {"vocab_order": (0, None)},
    "topics": {"topic_order": (0, None)},
    "senses": {"sense_order": (0, None)},
    "examples": {"video_start": (0, None)},
    "image_prompts": {"seed": (0, 2147483647), "attempts": (0, None)},
    "study_states": {
        "note_id": (0, None), "reps": (0, None), "lapses": (0, None),
        "stability": (0, None), "difficulty": (0, None), "retrievability": (0, 1),
    },
}

# The row a related id resolves to, or None. Supplied by the repository, so this module never learns
# what a database is.
Lookup = Callable[[str, str], Mapping[str, Any] | None]


def refuse(message: str) -> None:
    raise RecordRefused(message)


def _text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    return "" if value is None else str(value).strip()


def valid_language(value: Any, label: str) -> str:
    language = "" if value is None else str(value).strip()
    if not is_language(language):
        refuse(f"{label} must be a BCP-47 language tag.")
    return language


def string_array(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        refuse(f"{label} must be an array of non-empty strings.")
    if len(set(value)) != len(value):
        refuse(f"{label} must not contain duplicates.")


def gloss_array(value: Any) -> None:
    if not isinstance(value, list) or not value:
        refuse("Glosses must contain at least one language group.")
    seen: set[str] = set()
    for gloss in value:
        if not isinstance(gloss, dict):
            refuse("Each gloss must be an object.")
        language = valid_language(gloss.get("lang"), "Gloss language")
        if language in seen:
            refuse("Gloss languages must be unique within a sense.")
        seen.add(language)
        string_array(gloss.get("terms"), "Gloss terms")
        if not gloss.get("terms"):
            refuse("Each gloss must contain at least one term.")


def _related(lookup: Lookup, table: str, identifier: str, label: str) -> Mapping[str, Any]:
    row = lookup(table, identifier) if identifier else None
    if row is None:
        refuse(f"{label} does not exist.")
    return row  # type: ignore[return-value]


def _same_owner(row: Mapping[str, Any], parent: Mapping[str, Any], label: str) -> None:
    if row.get("owner") != parent.get("owner"):
        refuse(f"{label} must belong to the same owner.")


def _check_declared_bounds(name: str, row: Mapping[str, Any]) -> None:
    for field, (required, maximum) in TEXT_RULES.get(name, {}).items():
        value = _text(row, field)
        if required and not value:
            refuse(f"{field} is required.")
        if len(value) > maximum:
            refuse(f"{field} must be at most {maximum} characters.")
    for field, (allowed, required) in SELECT_RULES.get(name, {}).items():
        value = _text(row, field)
        if not value:
            if required:
                refuse(f"{field} is required.")
            continue
        if value not in allowed:
            refuse(f"{field} must be one of {', '.join(allowed)}.")
    for field, (minimum, maximum) in NUMBER_RULES.get(name, {}).items():
        value = row.get(field) or 0
        if value < minimum or (maximum is not None and value > maximum):
            refuse(f"{field} is out of range.")


def _sync_record(row: Mapping[str, Any]) -> None:
    if not is_record_id(str(row.get("id") or "")):
        refuse("Record ids must be 15 lowercase letters or digits.")
    if not is_instant(_text(row, "created_at")) or not is_instant(_text(row, "edited_at")):
        refuse("Record timestamps must be ISO-8601 UTC instants with milliseconds.")


def validate(name: str, row: Mapping[str, Any], lookup: Lookup) -> None:
    """Hold one record to every rule its collection carries. Raises `RecordRefused`."""
    _sync_record(row)
    _check_declared_bounds(name, row)

    if name == "vocabularies":
        valid_language(row.get("language"), "Vocabulary language")
        valid_language(row.get("definition_lang"), "Vocabulary definition language")
        gloss_langs = row.get("gloss_langs")
        string_array(gloss_langs, "Vocabulary gloss languages")
        if not gloss_langs:
            refuse("A vocabulary needs at least one gloss language.")
        for code in gloss_langs:  # type: ignore[union-attr]
            valid_language(code, "Vocabulary gloss language")
        valid_language(row.get("notes_lang"), "Vocabulary notes language")
        return

    if name == "topics":
        if not _text(row, "name"):
            refuse("Topic name is required.")
        return

    if name == "lexemes":
        language = valid_language(row.get("language"), "Lexeme language")
        # A prefix test, so `zh-Hant-TW` and `zho` both match. Narrowing this to equality would let a
        # Chinese entry through with no way to read it.
        if language.lower().startswith("zh") and not _text(row, "reading"):
            refuse("Chinese lexemes require a reading.")
        dialect = _text(row, "dialect")
        if dialect:
            valid_language(dialect, "Lexeme dialect")
        for topic_id in row.get("topics") or []:
            _same_owner(row, _related(lookup, "topics", topic_id, "Topic"), "Lexeme topic")
        string_array(row.get("notes"), "Notes")
        return

    if name == "senses":
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Sense")
        valid_language(row.get("definition_lang"), "Definition language")
        gloss_array(row.get("glosses"))
        return

    if name == "attestations":
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Attestation")
        if not is_instant(_text(row, "captured_at")):
            refuse("Capture timestamp must be an ISO-8601 UTC instant with milliseconds.")
        return

    if name == "examples":
        sense = _related(lookup, "senses", _text(row, "sense"), "Sense")
        _same_owner(row, sense, "Example")
        valid_language(row.get("text_lang"), "Example language")
        translation = _text(row, "translation")
        translation_language = _text(row, "translation_lang")
        if bool(translation) != bool(translation_language):
            refuse("Example translation and language must be provided together.")
        if translation_language:
            valid_language(translation_language, "Translation language")
        video_ref = _text(row, "video_ref")
        if not video_ref and (_text(row, "video_title") or (row.get("video_start") or 0) > 0):
            refuse("An example clip title or start time requires a video reference.")
        # Verbatim: untrimmed, uncased, un-normalised. Capture silently drops a form that fails this
        # exact test, so loosening it breaks the drop and tightening it turns a good capture into a
        # refusal.
        matched = _text(row, "matched_form")
        if matched and matched not in str(row.get("text") or ""):
            refuse("The matched form must occur in the example text.")
        matched_translation = _text(row, "matched_translation_form")
        if matched_translation and matched_translation not in translation:
            refuse("The matched translation form must occur in the example translation.")
        source_id = _text(row, "source_attestation")
        if _text(row, "origin") == "attestation" and not source_id:
            refuse("Attestation examples require a source attestation.")
        if source_id:
            attestation = _related(lookup, "attestations", source_id, "Source attestation")
            _same_owner(row, attestation, "Example source attestation")
            # The second hop. An attestation belonging to the right owner but the wrong word would
            # otherwise pass.
            if attestation.get("lexeme") != sense.get("lexeme"):
                refuse("Example source attestation and sense must belong to the same lexeme.")
        return

    if name == "image_prompts":
        lexeme = _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme")
        _same_owner(row, lexeme, "Image prompt")
        sense_id = _text(row, "sense")
        if sense_id:
            sense = _related(lookup, "senses", sense_id, "Sense")
            _same_owner(row, sense, "Image prompt sense")
            if sense.get("lexeme") != lexeme.get("id"):
                refuse("Image prompt sense must belong to its lexeme.")
        example_id = _text(row, "example")
        if example_id:
            example = _related(lookup, "examples", example_id, "Image prompt example")
            _same_owner(row, example, "Image prompt example")
            # The second hop, exactly as for an example's source attestation: an example belonging
            # to the right owner but the wrong sense would otherwise pass.
            if sense_id and example.get("sense") != sense_id:
                refuse("Image prompt example must belong to its sense.")
        # A brief the writer wrote is three fields or none of them: `compose()` needs the style to
        # build the prompt that was actually sent, and `prompt_version` is what says which template
        # and style table produced it. Half a brief reproduces nothing.
        if _text(row, "prompt") and not (_text(row, "style_id") and _text(row, "prompt_version")):
            refuse("An image brief must name the style and the prompt version it was written for.")
        # One direction, not both. A rendering model with nothing rendered is nonsense; a rendered
        # image with no model is a picture the owner attached themselves, which is how provenance is
        # modelled everywhere else here — an example the learner wrote carries no `model_id` either.
        if _text(row, "image_model_id") and not _text(row, "image_ref"):
            refuse("A rendering model without a rendered image is not a record of anything.")
        return

    if name == "study_states":
        _same_owner(row, _related(lookup, "lexemes", _text(row, "lexeme"), "Lexeme"), "Study state")
        card_ids = row.get("card_ids")
        if not isinstance(card_ids, list) or any(
            not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 0
            for identifier in card_ids
        ):
            refuse("Study-state card ids must be non-negative safe integers.")
        for field in ("last_review", "synced_at"):
            value = _text(row, field)
            if value and not is_instant(value):
                refuse(f"{field} must be an ISO-8601 UTC instant with milliseconds.")

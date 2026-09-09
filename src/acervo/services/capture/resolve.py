"""Model call one: what is this text about?"""

from __future__ import annotations

from typing import Any

from acervo.domain.validation import POS_VALUES
from acervo.errors import ApiError
from acervo.services.capture.coerce import (
    language_or_none,
    pick_choice,
    reference_of,
    trimmed,
)
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

UNREADABLE = ApiError(
    422, "unreadable_input", "That text could not be read as a word to learn, so nothing was created."
)


def resolve(
    settings: Settings, owner: str, request: dict[str, Any], vocabularies: list[dict]
) -> dict[str, Any]:
    stream = trimmed(request.get("mode")) == "stream"
    reference = reference_of(request)
    known = [
        entry["language"] + (f" ({entry['displayName']})" if entry.get("displayName") else "")
        for entry in vocabularies
    ]
    text = str(request.get("text") or "")
    lines = text.split("\n")
    user = "\n".join(
        line
        for line in [
            "Mode: " + ("stream" if stream else "single"),
            "Languages this learner studies: " + (", ".join(known) if known else "none configured yet"),
            f"The caller believes this is {trimmed(request.get('language'))}; verify it."
            if trimmed(request.get("language"))
            else "",
            f"The learner says the word is: {trimmed(request.get('headword'))}"
            if trimmed(request.get("headword"))
            else "",
            "\nReference (an external dictionary's entry for this word — CONTEXT ONLY. Do not\n"
            "take any sentence from it as one the learner supplied):\n```\n" + reference["text"] + "\n```"
            if reference
            else "",
            "",
            f"Input ({len(lines)} lines):",
            "```",
            text,
            "```",
        ]
        if line != ""
    )

    answer, _model = llm_json(
        settings, owner, prompt_text(settings.prompts_path, "acervo_resolve"), user
    )
    if isinstance(answer, dict) and trimmed(answer.get("error")):
        raise UNREADABLE
    if not isinstance(answer, dict):
        raise UNREADABLE
    language = language_or_none(answer.get("language"))
    headword = trimmed(answer.get("headword"))
    if not language or not headword:
        raise UNREADABLE

    try:
        consumed = round(float(answer.get("consumedLines") or 0))
    except (TypeError, ValueError):
        consumed = 0
    sentences = []
    for item in answer.get("sentences") or []:
        if not isinstance(item, dict):
            continue
        sentence = trimmed(item.get("text"))
        if not sentence:
            continue
        sentences.append({"text": sentence, "translation": trimmed(item.get("translation")) or None})

    # At least one line, always: a walk that consumes nothing loops on the same block forever.
    consumed_lines = max(1, min(consumed or 1, len(lines))) if stream else len(lines)
    consumed_text = trimmed(answer.get("consumedText"))
    if stream and consumed_text != "\n".join(lines[:consumed_lines]).strip():
        raise ApiError(
            502,
            "stream_boundary_mismatch",
            "The language model returned an unsafe stream boundary, so nothing was created.",
        )
    return {
        "language": language,
        "headword": headword,
        "lemma": trimmed(answer.get("lemma")) or headword,
        "pos": pick_choice(answer.get("pos"), POS_VALUES, "noun"),
        "sentences": sentences,
        "note": trimmed(answer.get("note")) or None,
        "consumedLines": consumed_lines,
        "consumedText": consumed_text or None,
    }

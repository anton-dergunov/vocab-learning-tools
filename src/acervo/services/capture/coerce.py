"""Reading the model's answer.

Everything here treats the response as untrusted input. A model that mislabels a part of speech or
marks a form that is not in its own sentence would otherwise fail record validation, and the whole
capture would surface to the owner as an anonymous refusal. Coerce what can be coerced, drop what
cannot, and never let a bad field abort an otherwise good entry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from acervo.domain.ids import is_language

REFERENCE_LIMIT = 8000


def trimmed(value: Any) -> str:
    return "" if value is None else str(value).strip()


def pick_choice(value: Any, allowed: Sequence[str], fallback: str | None) -> str | None:
    text = trimmed(value).lower()
    return text if text in allowed else fallback


def pick_optional_choice(value: Any, allowed: Sequence[str]) -> str | None:
    return pick_choice(value, allowed, None)


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    kept: list[str] = []
    for item in value:
        text = trimmed(item)
        if text and text not in kept:
            kept.append(text)
    return kept


def language_or_none(value: Any) -> str | None:
    text = trimmed(value)
    return text if is_language(text) else None


def reference_of(request: dict[str, Any]) -> dict[str, Any] | None:
    """An external dictionary's entry for the word, when the caller sent one.

    Grounding, and nothing else. It never reaches `resolution.sentences`, so it can never become an
    attestation: an attestation is a sentence the owner met, and a dictionary's own examples are not
    that. Provenance is modelled here, never flagged, and the modelling is this separation.
    """
    text = trimmed(request.get("reference"))
    if not text:
        return None
    mode = trimmed(request.get("referenceMode"))
    return {
        "text": text[:REFERENCE_LIMIT],
        "mode": mode if mode in ("faithful", "expand") else None,
    }

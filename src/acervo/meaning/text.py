"""What is embedded for a sense, and the digest that is its identity in the cache.

The sense, not the surface form: a bare word's embedding is dominated by spelling and frequency. The
template is the one `interest-aligned-vocabulary-recommendation`'s `discovery-v0.md` uses, so that
project can take these vectors rather than compute its own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any


def gloss_terms(glosses: Iterable[Mapping[str, Any]]) -> list[str]:
    return [str(term) for gloss in glosses or [] for term in (gloss.get("terms") or []) if str(term).strip()]


def sense_text(headword: str, pos: str, definition: str, glosses: Iterable[Mapping[str, Any]]) -> str:
    return f"{headword} ({pos}) — {definition.strip()} — {'; '.join(gloss_terms(glosses))}"


def digest(model: str, text: str) -> str:
    """The cache key, and so the whole of invalidation: an edit that changes what a sense says is a
    new key and is embedded again, and an edit that does not — a picture, an example — costs
    nothing."""
    return hashlib.sha256("\x1f".join((model, text)).encode("utf-8")).hexdigest()

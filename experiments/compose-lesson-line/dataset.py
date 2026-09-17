"""`words.yaml` turned into exactly what the shipped compose call takes.

Nothing here builds a request or reads a reply: `acervo.services.capture.compose.build_user_message`
and `acervo.services.capture.draft.draft_from` do both, so what is measured is the pipeline rather
than a copy of it. That is the same rule `experiments/clip-translation/dataset.py` lives by, and it
is the reason `build_user_message` was lifted out of `compose()` at all.

Resolve is deliberately skipped. `words.yaml` states the resolution — headword, lemma, part of
speech, language, the learner's sentences — because resolve is a separate prompt that this
experiment does not vary, and calling it would double the spend and add a second source of variance
to a paired comparison.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
WORDS = HERE / "words.yaml"


def load() -> dict[str, Any]:
    return yaml.safe_load(WORDS.read_text(encoding="utf-8"))


def digest() -> str:
    return hashlib.sha256(WORDS.read_bytes()).hexdigest()


def words(only: list[str] | None = None) -> list[dict[str, Any]]:
    rows = load()["words"]
    if not only:
        return rows
    wanted = set(only)
    unknown = wanted - {row["id"] for row in rows}
    if unknown:
        raise SystemExit(f"no such word(s) in words.yaml: {', '.join(sorted(unknown))}")
    return [row for row in rows if row["id"] in wanted]


def topics() -> list[dict[str, Any]]:
    """The owner's topic list, in the shape `owner_topics` returns: only `name` is read."""
    return [{"name": name} for name in load()["topics"]]


def vocabulary_for(word: dict[str, Any]) -> dict[str, Any]:
    return dict(load()["vocabularies"][word["language"]])


def resolution_for(word: dict[str, Any]) -> dict[str, Any]:
    """What the resolve call would have returned for this word."""
    return {
        "language": word["language"],
        "headword": word["headword"],
        "lemma": word["lemma"],
        "pos": word["pos"],
        "sentences": [
            {"text": one["text"], "translation": one.get("translation")}
            for one in word.get("sentences") or []
        ],
    }


def request_for(word: dict[str, Any]) -> dict[str, Any]:
    """The capture request body, carrying only what compose reads out of it."""
    return {"topics": list(word.get("topics") or [])}

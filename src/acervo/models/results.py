"""What every call returns beside its payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Answer:
    """Which row answered, how long it took, and what it cost.

    The old `ImageProvider.synthesize(...) -> None` is why this type exists: cost and model
    provenance had nowhere to go, so the pipeline that recorded both bypassed the layer entirely.
    It is also what the locked provenance contract requires — the entry records the model that
    *answered*, so the caller has to be told which one that was, not which one was asked first.
    """

    provider_id: str
    model: str
    seconds: float
    cost_usd: float | None
    warnings: tuple[str, ...] = ()
    attempts: tuple[str, ...] = ()  # provider ids tried, oldest first, including this one


@dataclass(frozen=True)
class TextResult:
    text: str
    parsed: Any | None  # set when the reply was asked for, and read, as JSON
    answer: Answer


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    answer: Answer


@dataclass(frozen=True)
class AudioResult:
    data: bytes
    mime: str
    answer: Answer

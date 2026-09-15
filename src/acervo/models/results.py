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
    # Every (provider id, model) pair tried, oldest first, including the one that answered. A
    # pair rather than a provider id because a row offers several models and the chain walks
    # them: two free tiers of 500 a day are reached one after the other, not one instead.
    attempts: tuple[tuple[str, str], ...] = ()
    # Every pair asked before this one, and what it said: (provider, model, reason). A fall-through
    # is otherwise invisible — the entry names who answered, but nothing says who was asked first or
    # why they were passed over, so a provider that is quietly broken looks like one nobody chose.
    passed_over: tuple[tuple[str, str, str], ...] = ()


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
    # The voice that actually spoke. A clip records it, so a voice changed later is detectable on the
    # clips made before the change rather than silently mixed in with them.
    voice: str | None = None

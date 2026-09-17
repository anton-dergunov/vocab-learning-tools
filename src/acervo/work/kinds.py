"""What a job kind is, and the registry of them (§4.14).

A kind declares a name, its steps, and a handler. It gets queuing, retry, pacing, cancellation, the
event stream and the progress strip without writing any of them — which is the whole contract a
future processor has to meet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acervo.work.runner import JobContext


@dataclass(frozen=True)
class Kind:
    name: str
    # Declared up front, so the owner sees every phase from the moment the job starts.
    steps: tuple[str, ...]
    handler: Callable[["JobContext"], None]


_registry: dict[str, Kind] = {}


def register(kind: Kind) -> Kind:
    _registry[kind.name] = kind
    return kind


def unregister(name: str) -> None:
    _registry.pop(name, None)


def find(name: str) -> Kind | None:
    _load()
    return _registry.get(name)


def names() -> tuple[str, ...]:
    _load()
    return tuple(_registry)


_loaded = False


def _load() -> None:
    """Import the modules that register the shipped kinds, once."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from acervo.work import capture, enrich  # noqa: F401 - each registers itself

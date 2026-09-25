"""Something changed: the one in-process signal between the writers and whoever is listening.

Two messages, and neither carries a record (`docs/architecture/server.md`, "Jobs"):

- `revision`: this owner's counter moved, so a client should pull;
- `job`: a job's state or steps changed, so a client can show it.

Records still reach a replica only through the cursor pull, so there is still exactly one way a
replica changes. This module is also what wakes the runner when work is queued in this process; a
job queued by another process (`admin jobs …`) is found by the runner's own poll instead.

It imports nothing of Acervo's, so the repository, the runner and the event route can all depend on
it without depending on each other.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

# Set whenever work is queued in this process. The runner clears it before it looks for a job and
# waits on it when it finds none, so a job queued in between is never slept through.
work_arrived = threading.Event()


class _Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids = itertools.count()
        self._subscribers: dict[int, tuple[str, asyncio.AbstractEventLoop, asyncio.Queue]] = {}

    @contextmanager
    def subscribe(self, owner: str) -> Iterator[asyncio.Queue]:
        """A queue of this owner's messages, for as long as the block runs. Call from an event loop."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        key = next(self._ids)
        with self._lock:
            self._subscribers[key] = (owner, loop, queue)
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.pop(key, None)

    def publish(self, owner: str, message: Mapping[str, Any]) -> None:
        """Hand a message to every listener of this owner. Safe from any thread; never blocks."""
        with self._lock:
            listeners = [(loop, queue) for who, loop, queue in self._subscribers.values()
                         if who == owner]
        for loop, queue in listeners:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, dict(message))
            except RuntimeError:
                # The listener's loop has closed; its `finally` is about to remove it.
                pass

    def listening(self) -> int:
        with self._lock:
            return len(self._subscribers)


hub = _Hub()


def revision(owner: str, cursor: int) -> None:
    hub.publish(owner, {"type": "revision", "cursor": cursor})


def job(owner: str, projected: Mapping[str, Any]) -> None:
    hub.publish(owner, {"type": "job", "job": projected})


def queued(owner: str, projected: Mapping[str, Any]) -> None:
    """A job was queued: tell the owner, and wake the runner."""
    job(owner, projected)
    work_arrived.set()

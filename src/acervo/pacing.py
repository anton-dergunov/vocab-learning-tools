"""One shared gate in front of the image model.

A new Vertex project has a small per-minute allowance for the image models, and a pool of workers
discovers that by all being refused at once. Two things fix it, and both have to be shared across
threads rather than per job:

- a sliding window, so the pool never offers more requests per minute than the allowance;
- a cooldown that every worker respects, so one 429 pauses the whole pool instead of each worker
  backing off privately and arriving together again.

Shared rather than image-only: the file ingestion runs beside this and needs the same gate.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Sequence

WINDOW = 60.0


class Pace:
    def __init__(self, per_minute: int, *, cooldown: float = 30.0, cap: float = 300.0) -> None:
        self.per_minute = max(0, int(per_minute))
        self.base_cooldown = cooldown
        self.cap = cap
        self._lock = threading.Lock()
        self._calls: deque[float] = deque()
        self._until = 0.0
        self._streak = 0
        self.waited = 0.0

    def _delay_locked(self, now: float) -> float:
        """Seconds until this gate would let a call through. Zero means now. Caller holds the lock."""
        if now < self._until:
            return self._until - now
        while self._calls and now - self._calls[0] > WINDOW:
            self._calls.popleft()
        if not self.per_minute or len(self._calls) < self.per_minute:
            return 0.0
        return self._calls[0] + WINDOW - now

    def try_acquire(self) -> bool:
        """Take a slot if one is free right now. Never blocks."""
        with self._lock:
            now = time.time()
            if self._delay_locked(now) > 0:
                return False
            self._calls.append(now)
            return True

    def delay(self) -> float:
        with self._lock:
            return self._delay_locked(time.time())

    def acquire(self) -> None:
        """Block until this thread may call. Never holds the lock while sleeping."""
        while True:
            with self._lock:
                delay = self._delay_locked(time.time())
                if delay <= 0:
                    self._calls.append(time.time())
                    return
            with self._lock:
                self.waited += delay
            time.sleep(delay)

    def penalise(self) -> float:
        """A refusal for quota. Pause every worker, longer each time it keeps happening."""
        with self._lock:
            self._streak += 1
            delay = min(self.base_cooldown * (2 ** (self._streak - 1)), self.cap)
            self._until = max(self._until, time.time() + delay)
            return delay

    def succeeded(self) -> None:
        with self._lock:
            self._streak = 0


def is_quota_error(error: BaseException) -> bool:
    text = str(error)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()


class ModelPool:
    """Several image models, each with its own quota bucket.

    Measured on 2026-09-05: this project is allowed roughly **one image request per minute per
    model** — the gaps between successive images in a 39-minute run had a median of 60.5s, and a
    429 comes back in about a tenth of a second, so it is a refill rate and not a concurrency
    limit. No amount of worker tuning moves that ceiling.

    Two models therefore run at twice the rate of one, because the buckets are separate. This
    hands each caller whichever model is free soonest, so a slow model never holds up a free one.
    """

    def __init__(self, models: Sequence[tuple[str, int]], *, cooldown: float = 30.0) -> None:
        if not models:
            raise ValueError("A model pool needs at least one model.")
        self.gates = {model: Pace(per_minute, cooldown=cooldown) for model, per_minute in models}

    def acquire(self) -> str:
        """Block until some model is free, then return it with its slot already taken."""
        while True:
            for model, gate in self.gates.items():
                if gate.try_acquire():
                    return model
            time.sleep(min(max(gate.delay() for gate in self.gates.values()) and
                           min(gate.delay() for gate in self.gates.values()), 5.0) or 0.25)

    def penalise(self, model: str) -> float:
        return self.gates[model].penalise()

    def succeeded(self, model: str) -> None:
        self.gates[model].succeeded()

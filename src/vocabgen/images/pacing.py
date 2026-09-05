"""One shared gate in front of the image model.

A new Vertex project has a small per-minute allowance for the image models, and a pool of workers
discovers that by all being refused at once. Two things fix it, and both have to be shared across
threads rather than per job:

- a sliding window, so the pool never offers more requests per minute than the allowance;
- a cooldown that every worker respects, so one 429 pauses the whole pool instead of each worker
  backing off privately and arriving together again.

Deliberately not `provider/rate_limiter.py`: that one is not thread-safe, and it is imported by the
ingestion running beside this.
"""

from __future__ import annotations

import threading
import time
from collections import deque

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

    def acquire(self) -> None:
        """Block until this thread may call. Never holds the lock while sleeping."""
        while True:
            with self._lock:
                now = time.time()
                if now < self._until:
                    delay = self._until - now
                else:
                    while self._calls and now - self._calls[0] > WINDOW:
                        self._calls.popleft()
                    if not self.per_minute or len(self._calls) < self.per_minute:
                        self._calls.append(now)
                        return
                    delay = self._calls[0] + WINDOW - now
            if delay > 0:
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

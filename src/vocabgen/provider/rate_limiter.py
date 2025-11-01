import time
import logging
from collections import deque
from typing import Optional

# TODO Would it be better to use vocabgen.llm.rate_limiter?
logger = logging.getLogger("llm.rate_limiter")


class RateLimiter:
    """
    Simple sliding-window rate limiter: max_calls per minute.
    If max_calls is None or <= 0, no limiting is applied.
    """

    WINDOW_SECONDS: float = 60.0

    def __init__(self, max_calls_per_minute: Optional[int] = None):
        self.max_calls = int(max_calls_per_minute) if max_calls_per_minute else None
        # store timestamps (float seconds) of recent calls
        self._timestamps = deque()

    def _clear_old_timestamps(self):
        now = time.time()
        while self._timestamps and (now - self._timestamps[0]) > self.WINDOW_SECONDS:
            self._timestamps.popleft()

    def acquire(self) -> None:
        """Block until a request is allowed under the configured rate limit."""
        if not self.max_calls:
            return

        self._clear_old_timestamps()
        now = time.time()
        if len(self._timestamps) < self.max_calls:
            # Allow immediately
            self._timestamps.append(now)
            return

        # Need to wait until the oldest timestamp is older than window_seconds
        oldest = self._timestamps[0]
        sleep_for = (oldest + self.WINDOW_SECONDS) - now
        logger.debug("Rate limit reached: sleeping %.2fs", sleep_for)
        if sleep_for > 0:
            time.sleep(sleep_for)

        # After sleeping, append new timestamp (and cleanup)
        self._clear_old_timestamps()
        self._timestamps.append(time.time())

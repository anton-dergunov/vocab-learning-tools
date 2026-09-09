"""What a refusal tells the *next* request.

Without this, every capture re-walks the chain from the top. A free tier exhausted at ten in the
morning is then a wasted 429 on every entry until it resets — twice over, where a row offers two
models — and the owner pays for it in latency on every single word.

The obvious fixes are both wrong. Switching an exhausted model off needs someone to switch it back
on, and they will not be watching at the moment the quota resets. Hard-coding when each provider
resets needs a fact nobody has: Gemini's free tier rolls over at an hour this project does not know,
Cloudflare's is a different hour, and a provider is free to change its mind.

So: a refusal is remembered as a **hint about ordering, and never as a reason to refuse**. A pair
that has just been rate limited goes to the back of the queue for a while. When *every* pair is
resting the rests are ignored and the chain is walked as written — which is what makes recovery
automatic and needs no reset time to be known. The first request after a quota rolls over pays one
ordinary call and finds the model working again.

It is deliberately in-process and deliberately not persisted. A rest is a guess about the next few
minutes; carrying it across a restart would mean carrying a guess made under conditions that no
longer hold, and it would need a schema.
"""

from __future__ import annotations

import threading
import time
from typing import Iterable, Sequence

Pair = tuple[str, str]

# How long a pair rests, by what went wrong. A rate limit is the long one: it means an allowance is
# spent, and allowances refill on the provider's clock rather than in seconds. The others are short
# because a 5xx or a dropped connection is usually over by the time you look again.
#
# The rate-limit rest is deliberately far shorter than a day. It does not need to cover the wait —
# "everything is resting" already handles that — it only needs to be long enough that a spent
# allowance is not re-probed on every entry.
REST: dict[str, float] = {
    "rate_limited": 900.0,
    "unavailable": 60.0,
    "unreachable": 60.0,
}
LONGEST = 3600.0


class Rests:
    """Which pairs are resting, and until when. Safe to share across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._until: dict[Pair, float] = {}
        self._streak: dict[Pair, int] = {}

    def note(self, pair: Pair, reason: str, *, retry_after: float | None = None) -> float:
        """Record a refusal. Returns how long this pair will rest, in seconds.

        `retry_after` is the provider's own answer where it gave one, and it is trusted over the
        table: nobody else knows when that allowance refills. Otherwise the rest doubles while a
        pair keeps failing, so a model that is down all afternoon is asked about progressively less.
        """
        base = REST.get(reason)
        if base is None:
            return 0.0  # a terminal refusal stops the chain outright; resting it would say nothing
        with self._lock:
            streak = self._streak.get(pair, 0) + 1
            self._streak[pair] = streak
            resting = retry_after if retry_after is not None else min(base * 2 ** (streak - 1), LONGEST)
            self._until[pair] = time.monotonic() + resting
            return resting

    def succeeded(self, pair: Pair) -> None:
        with self._lock:
            self._until.pop(pair, None)
            self._streak.pop(pair, None)

    def resting(self, pair: Pair) -> bool:
        with self._lock:
            until = self._until.get(pair)
            if until is None:
                return False
            if time.monotonic() >= until:
                del self._until[pair]
                return False
            return True

    def ready(self, pairs: Sequence[Pair]) -> tuple[Pair, ...]:
        """The pairs worth asking first, or all of them when every one is resting.

        The fallback is the whole point. A rest must never be able to empty a chain: an owner who
        has chosen one model would otherwise find capture switched off by a single 429, and nothing
        would switch it back on until somebody guessed the provider's reset hour.
        """
        awake = tuple(pair for pair in pairs if not self.resting(pair))
        return awake or tuple(pairs)

    def forget_all(self) -> None:
        """Drop every rest. For tests, and for anything that wants a clean probe."""
        with self._lock:
            self._until.clear()
            self._streak.clear()


rests = Rests()


def retry_after_of(error: BaseException) -> float | None:
    """The provider's own "come back in N seconds", when it sent one.

    Read from the response headers only. Some providers also put a delay in the error body, in a
    shape of their own devising, and parsing those here would be per-provider code in the one place
    this package keeps free of it.
    """
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after")
    except Exception:  # noqa: BLE001 — a header bag of unknown provenance
        return None
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except ValueError:
        return None  # the HTTP-date form; rare here, and the table is a fine answer
    return min(max(seconds, 0.0), LONGEST)


def note_all(pairs: Iterable[Pair], reason: str) -> None:
    """Rest several pairs at once, for a refusal that was about the provider rather than the model."""
    for pair in pairs:
        rests.note(pair, reason)

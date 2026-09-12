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

import re
import threading
import time
from typing import Iterable, Sequence

Pair = tuple[str, str]

# How long a pair rests when the provider does not say, by what went wrong.
#
# **A 429 does not say whether an allowance was per minute or per day**, and both arrive
# identically: Gemini answers "Quota exceeded for metric … requests" whether fifteen-a-minute or
# five-hundred-a-day ran out. So the first rest is short enough for the per-minute case — the free
# tier allows 15 text requests a minute and 3 speech ones, so half a minute usually clears it — and
# the *doubling* is what reaches a spent daily quota without ever having to tell the two apart. A
# model that keeps refusing is asked about progressively less: 30s, 1m, 2m, 4m … up to the cap.
#
# Starting long would have been the worse mistake in both directions. It leaves a working model
# unused for an hour after a momentary burst, and it costs nothing to be wrong the other way: an
# early probe is one 429, which comes back in about a tenth of a second.
#
# `unusable` and `empty` are in the table for a different reason, and it is worth saying which.
# Nothing here ever sleeps — `ready` only reorders — so a rest is a *demotion*, not a wait. A model
# that answered with the wrong shape will answer with the wrong shape again in thirty seconds, so
# there is nothing to wait out; what there is, is a reason to try somebody else first. Leaving them
# out meant `note` returned zero, the pair was never demoted, and every later call re-probed the one
# model that could not do the job, from the head of the chain, forever.
REST: dict[str, float] = {
    "rate_limited": 30.0,
    "unavailable": 20.0,
    "unreachable": 20.0,
    "unusable": 30.0,
    "empty": 30.0,
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


# "Please retry in 54.106058949s." and `"retryDelay": "54s"` — the two shapes Google's own
# RetryInfo reaches us in. Deliberately narrow: a duration, in seconds, and nothing else.
_SPOKEN_DELAY = re.compile(r"retry(?:\s+in|Delay\"?\s*[:=]\s*\"?)\s*([0-9]+(?:\.[0-9]+)?)\s*s", re.I)


def retry_after_of(error: BaseException) -> float | None:
    """The provider's own "come back in N seconds", when it said one. None when it did not.

    Two sources, because providers disagree about where to put it. OpenAI and friends send a
    `Retry-After` header. Google sends neither a header nor a readable body by the time LiteLLM is
    finished with it — measured, not assumed: the response arrives here with empty headers and an
    unparseable body — and puts the delay in the message instead.

    Reading a number out of a message is exactly the string-matching this package replaced with
    typed errors, so it is worth being clear about why it is allowed *here* and not there. The old
    `is_quota_error` matched text to decide whether a failure was retryable at all — a correctness
    decision, where a missed match changed what happened. This decides only *when to probe again*,
    the fallback is total, and being wrong costs one cheap 429. A hint, held to a hint's standard.
    """
    for value in (_header_delay(error), _spoken_delay(error)):
        if value is not None:
            return min(max(value, 0.0), LONGEST)
    return None


def _header_delay(error: BaseException) -> float | None:
    headers = getattr(getattr(error, "response", None), "headers", None)
    try:
        value = headers.get("retry-after") if headers is not None else None
    except Exception:  # noqa: BLE001 — a header bag of unknown provenance
        return None
    try:
        return float(str(value).strip()) if value is not None else None
    except ValueError:
        return None  # the HTTP-date form; rare here, and the table is a fine answer


def _spoken_delay(error: BaseException) -> float | None:
    found = _SPOKEN_DELAY.search(str(error))
    return float(found.group(1)) if found else None


def note_all(pairs: Iterable[Pair], reason: str) -> None:
    """Rest several pairs at once, for a refusal that was about the provider rather than the model."""
    for pair in pairs:
        rests.note(pair, reason)

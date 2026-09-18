"""Whether to ask again, and when. The one place a retry is decided (§4.5).

The provider chain still decides *which* pair answers, with its fall-through, hedging and rests;
this decides whether the runner tries the whole step again after the chain has given up. Only three
failures are worth that — a quota, a busy provider, a dropped connection — and every other one is a
fact to record rather than a condition to wait out.
"""

from __future__ import annotations

from acervo.models.pacing import Pace

# The three model-call failures, and the two the loop generator can answer with that mean the same
# two things: it is busy with another render, or the container is not there this second. Both are
# conditions that pass on their own. `loops_failed` is not among them — a render the generator ran
# and could not finish is a fact about that request, and asking again changes nothing.
TRANSIENT = frozenset({
    "llm_rate_limited", "llm_unavailable", "llm_unreachable",
    "loops_busy", "loops_unreachable",
})

# A step waits 30 seconds, doubling to ten minutes, and gives up after this many rests — about 25
# minutes in all. Past that, the provider is not having a bad minute, and the word is better left
# usable with a Try again than held open for an afternoon.
FIRST_REST = 30.0
LONGEST_REST = 600.0
MAX_RESTS = 6

# One gate per lane, shared by every job, because one process now does all the work. A lane is the
# kind of allowance a step spends: a quota refused for pictures says nothing about clip searches.
# Zero calls per minute means "no window, only the rest after a refusal".
LANES: dict[str, int] = {
    "text": 10,
    "clip": 0,
    "image": 0,
    "audio": 0,
    "corpus": 0,
}


def lanes() -> dict[str, Pace]:
    return {
        name: Pace(per_minute, cooldown=FIRST_REST, cap=LONGEST_REST)
        for name, per_minute in LANES.items()
    }


def is_transient(code: str | None) -> bool:
    return code in TRANSIENT

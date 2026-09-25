"""Whether to ask again, and when. The one place a retry is decided (`docs/architecture/jobs.md`).

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

# A story is nothing at all until its first step succeeds, so giving up is not "leave it usable and
# let the owner try again" — it is a row of Try again buttons. Twenty rests is about three hours:
# long enough to outlast an outage like the one on 24 Sep 2026, when Gemini's free tier answered 503
# for an hour while Cloudflare's daily allowance had already gone, and twelve stories asked for in a
# row all failed one after another at the 25-minute mark.
STORY_RESTS = 20

# One gate per lane, shared by every job, because one process now does all the work. A lane is the
# kind of allowance a step spends: a quota refused for pictures says nothing about clip searches.
# Zero calls per minute means "no window, only the rest after a refusal".
LANES: dict[str, int] = {
    "text": 10,
    "clip": 0,
    # One picture a minute is the allowance measured for the Vertex image model (a median gap of
    # 60.5 s over a 39-minute run, 5 Sep 2026), and on 24 Sep it answered two in a row and then 429
    # every time, a bucket of two refilling at one a minute. Discovering that by refusal cost a rest
    # that doubled towards ten minutes while pictures were in fact being drawn; keeping to it costs a
    # minute between pictures, and the other jobs in the lane take their turns in between.
    "image": 1,
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

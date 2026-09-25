"""`loop`: ask the generator for a track, follow it, and store what comes back.

The work happens in the companion container — seventy-odd model calls, a procedural bed and a mix —
which is what keeps the runner's rule (`docs/architecture/jobs.md`) — *"anything heavy is out of
scope for the runner"* — true rather than merely restated. This job holds a lane and a poll timer.

It follows an operation exactly as `work/corpus.py` does, and deliberately: the generator answers the
same `operation_id` / `status` / `successful` / `error` vocabulary the corpus does, so this is a
second instance of one pattern rather than a second pattern.

Nothing resumes across a restart. A render still running when the process stops is marked interrupted
and Try again queues a new one — which costs latency rather than money, because the takes it already
paid for are in the cache and the next render finds them.

**Nothing is held in memory between the two steps.** The render writes the operation's id down and
the store reads it back and asks the generator again, rather than being handed the finished object:
a step that fails and is retried re-enters the handler from the top with only what was written down,
so an in-memory hand-off is a hand-off that works until the first retry.
"""

from __future__ import annotations

from acervo.errors import ApiError
from acervo.services import loops
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Requeue, Step

# What the graph records as having written a loop. A device id like any other writer's, and the same
# one the enrichment job uses: both are this server doing its own work.
DEVICE = "acervorunner"

# How long between looks at a running render. Measured rather than guessed: three words took 65 s,
# about 3.6 s an utterance, so a twelve-word loop is roughly four and a half minutes. Five seconds
# puts about fifty progress readings across one, which is what makes the strip move rather than sit.
POLL_SECONDS = 5.0
# How many looks before the job stops following: half an hour. The render carries on in the
# generator either way; this only stops a job staying open for one that never reports an end. A
# twelve-word loop at the measured rate is a tenth of this.
MAX_POLLS = 360


def _render(context: JobContext, step: Step, loop_id: str) -> str | None:
    """Start the render, or look at the one this job already started."""
    step.gate()
    detail = step.record.get("detail") or {}
    operation_id = detail.get("operationId")

    if operation_id:
        operation = loops.follow(context.settings, operation_id)
    else:
        # A change of music carries its seed here rather than on the row, which goes on describing
        # the track it holds until the new one lands; see `services/loops.music`.
        seed = str(context.input.get("seed") or "").strip()
        request = loops.render_request(context.settings, context.owner, loop_id,
                                       seed=int(seed) if seed.isdigit() else None)
        family = str(context.input.get("family") or "").strip()
        operation = loops.start(context.settings, request, **({"family": family} if family else {}))
        step.note(operationId=operation.id, delivery=loops.delivery(context.owner),
                  family=family or "auto", words=len(request["items"]))

    if not operation.finished:
        polls = int(detail.get("polls") or 0) + 1
        if polls > MAX_POLLS:
            raise ApiError(504, "loops_timeout",
                           "The loop has not finished after half an hour; stopped following it.")
        step.record["state"] = "waiting"
        step.note(operationId=operation.id, status=operation.status, polls=polls,
                  progress=round(operation.fraction, 3), doing=operation.message)
        raise Requeue(POLL_SECONDS)

    step.note(status=operation.status, successful=operation.successful)
    if operation.status != "completed" or operation.result is None:
        raise ApiError(502, "loops_failed", operation.error or f"The render was {operation.status}.")
    step.note(styleId=operation.result.style_id, seconds=round(operation.result.duration_seconds, 1))
    return None


def _store(context: JobContext, step: Step, loop_id: str) -> str | None:
    """Fetch the track the render made and write it, with the times, into the graph."""
    operation_id = (context.record("loop.render").get("detail") or {}).get("operationId")
    if not operation_id:
        raise ApiError(502, "loops_failed", "The render did not say which operation it started.")
    operation = loops.follow(context.settings, operation_id)
    if operation.result is None:
        raise ApiError(502, "loops_failed", operation.error or "The render produced no track.")
    stored = loops.store(context.settings, context.owner, DEVICE, loop_id, operation.result)
    step.note(audioRef=stored.get("audioRef"))
    return None


def render(context: JobContext) -> None:
    loop_id = context.subject_id
    # The audio lane, because that is the allowance this actually spends: the generator holds no
    # credential and speaks every line by calling home to `POST /pronunciations/take`. A quota
    # refused for a loop is the same quota a word's pronunciation would have been refused from.
    context.step("loop.render", lambda step: _render(context, step, loop_id), lane="audio")
    context.step("loop.store", lambda step: _store(context, step, loop_id))


register(Kind("loop", ("loop.render", "loop.store"), render))

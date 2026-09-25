"""`corpus.update`: ask the corpus to fetch and reindex, and follow it (`docs/architecture/server.md`, "Jobs").

The work happens in the retrieval service. This job starts it — or joins the one already running —
and checks on it every so often, putting itself back to wait in between rather than holding the
runner's one lane for however long a channel scan takes.
"""

from __future__ import annotations

from acervo.errors import ApiError
from acervo.services import corpus
from acervo.work.kinds import Kind, register
from acervo.work.runner import JobContext, Requeue, Step

# How long between looks at a running operation. An update takes minutes; a word saved meanwhile
# is enriched in between.
POLL_SECONDS = 20.0
# How many looks before the job stops following: six hours. The operation carries on in the corpus
# either way; this only stops a job staying open for an update that never reports an end.
MAX_POLLS = 1080


def follow(context: JobContext, step: Step) -> str | None:
    if not corpus.configured(context.settings):
        return "skipped"
    step.gate()
    detail = step.record.get("detail") or {}
    operation_id = detail.get("operationId")
    if operation_id:
        operation = corpus.operation(context.settings, operation_id)
    else:
        operation = corpus.start_update(context.settings)
        step.note(operationId=operation.id)
    if not operation.finished:
        polls = int(detail.get("polls") or 0) + 1
        if polls > MAX_POLLS:
            raise ApiError(504, "corpus_timeout",
                           "The corpus update has not finished after six hours; stopped following it.")
        step.record["state"] = "waiting"
        step.note(operationId=operation.id, status=operation.status, polls=polls)
        raise Requeue(POLL_SECONDS)
    step.note(status=operation.status, successful=operation.successful)
    if operation.status != "completed":
        raise ApiError(502, "corpus_failed", operation.error or f"The corpus update was {operation.status}.")
    if operation.successful is False:
        raise ApiError(502, "corpus_incomplete",
                       "The corpus was updated, but some channels could not be fetched.")
    return None


def update(context: JobContext) -> None:
    context.step("corpus.update", lambda step: follow(context, step), lane="corpus")


register(Kind("corpus.update", ("corpus.update",), update))

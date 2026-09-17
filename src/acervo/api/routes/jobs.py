"""Reading the work the server is doing, and asking for more (`docs/plans/processing-flow.md` §4.8).

A route queues a job and reads its record; it never runs one. That is `acervo.work`'s, which this
package reaches only through `repository.jobs`.

Only the kinds a person can ask for directly are accepted here. A save queues `enrich` on its own;
this is for Try again, and for a bundle import that restores pictures before it asks for the rest.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.domain.ids import is_record_id
from acervo.errors import ApiError
from acervo.repository import graph, jobs

router = APIRouter()

# kind → what its subject must be. Grows as the interface gains a way to ask for each.
ENQUEUEABLE: dict[str, str] = {
    "enrich": "lexeme",
}
TRIGGERS = ("manual", "import")

NOT_FOUND = ApiError(404, "not_found", "There is no such job.")


def _subject(owner: str, kind: str, body: dict[str, Any]) -> str:
    expected = ENQUEUEABLE[kind]
    subject = body.get("subject") if isinstance(body.get("subject"), dict) else {}
    identifier = str(subject.get("id") or "").strip()
    if subject.get("kind") != expected or not is_record_id(identifier):
        raise ApiError(400, "invalid_input", f"A {kind} job is about one {expected}.")
    if graph.lexeme_of(owner, expected, identifier) is None:
        raise ApiError(404, "not_found", "That word is not in your vocabulary.")
    return identifier


@router.get("/jobs")
def list_jobs(request: Request) -> JSONResponse:
    """Open jobs with `?open=true` — what a client rebuilds its map from — else recent ones."""
    account = owner_id(request)
    if request.query_params.get("open") == "true":
        return data({"jobs": jobs.open_jobs(account)})
    try:
        limit = int(request.query_params.get("limit") or 50)
    except ValueError:
        limit = 50
    return data({"jobs": jobs.recent(account, limit)})


@router.get("/jobs/{job_id}")
def read_job(job_id: str, request: Request) -> JSONResponse:
    found = jobs.get(owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)


@router.post("/jobs")
async def enqueue(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    kind = str(body.get("kind") or "")
    if kind not in ENQUEUEABLE:
        raise ApiError(400, "invalid_input", f"A {kind or 'nameless'} job cannot be asked for.")
    trigger = str(body.get("trigger") or "manual")
    if trigger not in TRIGGERS:
        raise ApiError(400, "invalid_input", "A job is asked for manually or by an import.")
    subject = await run_in_threadpool(_subject, account, kind, body)
    queued = await run_in_threadpool(
        jobs.enqueue, account, kind, trigger=trigger,
        subject_kind=ENQUEUEABLE[kind], subject_id=subject,
    )
    return data(queued, status=202)


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str, request: Request) -> JSONResponse:
    found = await run_in_threadpool(jobs.request_cancel, owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)


@router.post("/jobs/{job_id}/dismiss")
async def dismiss(job_id: str, request: Request) -> JSONResponse:
    found = await run_in_threadpool(jobs.dismiss, owner_id(request), job_id)
    if found is None:
        raise NOT_FOUND
    return data(found)

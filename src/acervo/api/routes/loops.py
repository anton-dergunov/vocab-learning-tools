"""Making a loop, and reading what the generator can be asked for.

- `POST /loops` writes the loop and its words and queues the render. It takes **word ids**, never a
  query: the interface sampled them from the scope on screen and the server does not re-derive that
  scope. Choosing words by hand is therefore the same route with a different list, and no server
  change at all.
- `GET /loops/schema` is an **allow-listed passthrough**, and one route rather than a prefix: each is
  written out, so a route the generator grows never silently becomes an Acervo route, and no path a
  client sends is concatenated into a URL. That is the rule `api/routes/speech.py` already lives by.

It answers Acervo's own `{"data": …}` envelope rather than the generator's body verbatim. The speech
proxy is the one exception in this API, and it exists to keep a packaged typed client working; there
is no such client here, and a second exception would make the first one a pattern.

`POST /loops` writes the row **and then** queues the job, in that order and not atomically. If the
queue fails, the loop shows as never rendered and Try again queues another — which is §2.9's derived
state doing its job rather than a gap.

Not `schemaVersion`-gated, for `images.py`'s reason: the rows this writes go through `merge_graph`
and are gated there like every other write.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import graph, jobs
from acervo.services.loops import create, schema

router = APIRouter()


@router.get("/loops/schema")
async def read_schema(request: Request) -> JSONResponse:
    """What the generator offers: its patterns, its families, and whether it has its samples."""
    owner_id(request)
    return data(await run_in_threadpool(schema, request.app.state.settings))


@router.post("/loops")
async def make(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    device = graph.require_device(body.get("deviceId"))

    loop = await run_in_threadpool(create, request.app.state.settings, owner, device, body)
    # The row exists whether or not this succeeds, which is the point: a queue that failed leaves a
    # loop that was asked for and not made, and that is exactly what an empty `audioRef` says.
    queued = await run_in_threadpool(
        lambda: jobs.enqueue(owner, "loop", trigger="manual", subject_kind="loop",
                             subject_id=loop["id"], input={})
    )
    return data({"loop": loop, "job": queued}, status=202)

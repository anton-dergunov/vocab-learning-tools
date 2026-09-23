"""Making a loop, and reading what the generator can be asked for.

- `POST /loops` writes the loop and its words and queues the render. It takes **word ids**, never a
  query: the interface sampled them from the scope on screen and the server does not re-derive that
  scope. Choosing words by hand is therefore the same route with a different list, and no server
  change at all.
- `POST /loops/{id}/music` renders a loop again with other music: a family, a seed, or both (a
  favourite). It queues the same `loop` job with those as its input and leaves the row alone, so the
  loop goes on describing the track it holds until the new one lands and replaces it.
- `DELETE /loops/{id}` tombstones the loop and its words and unlinks the track. It is a route
  rather than an ordinary client write for the reason the image routes are: a track is megabytes,
  nothing else would ever remove it, and the row and the file have to be written by the same party.
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
from acervo.errors import ApiError
from acervo.repository import graph, jobs
from acervo.services.loops import create, music, remove, schema

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
    # The chosen music rides on the job rather than on the row: it is an instruction for the render,
    # not a fact about the loop — the loop's own `styleId` is what the render *chose*. Carrying it
    # here is also what makes Try again ask for the same music, since a re-enqueue reuses `input`.
    family = str(body.get("family") or "").strip()
    queued = await run_in_threadpool(
        lambda: jobs.enqueue(owner, "loop", trigger="manual", subject_kind="loop",
                             subject_id=loop["id"], input={"family": family} if family else {})
    )
    return data({"loop": loop, "job": queued}, status=202)


@router.post("/loops/{loop_id}/music")
async def change_music(loop_id: str, request: Request) -> JSONResponse:
    """New music for a loop: another style, the same style afresh, or a kept favourite."""
    owner = owner_id(request)
    body = await json_body(request)
    # One render at a time for a loop. A second request would queue behind the first, and the one
    # the owner is waiting to hear would be replaced by the other a few minutes later.
    if await run_in_threadpool(jobs.open_for, owner, "loop", loop_id) is not None:
        raise ApiError(409, "loop_busy", "This loop is already being made; wait for it to finish.")
    given = await run_in_threadpool(music, request.app.state.settings, owner, loop_id, body)
    queued = await run_in_threadpool(
        lambda: jobs.enqueue(owner, "loop", trigger="manual", subject_kind="loop",
                             subject_id=loop_id, input=given)
    )
    return data({"job": queued}, status=202)


@router.delete("/loops/{loop_id}")
async def drop(loop_id: str, request: Request) -> JSONResponse:
    """Delete a loop, its words and its track."""
    owner = owner_id(request)
    device = graph.require_device(request.headers.get("x-acervo-device"))
    return data(
        await run_in_threadpool(remove, request.app.state.settings, owner, device, loop_id)
    )

"""Drawing a sense picture, one model call per request.

Five routes, and the unit of every one of them is a single model call. That granularity is not
symmetry with capture: `web/src/api.ts` gives an ordinary request 15 seconds and capture 300, while
an image takes 30–60 and providers meter roughly one a minute. A route that briefed and drew a whole
word would outlive even the capture timeout while the server kept working — the client would retry,
and the picture would be drawn, and billed, twice.

Three named actions rather than one that guesses, because they cost different things: **draw again**
is one image call with a fresh seed, **write a new brief** is one text call for the whole word, and
**edit and draw** costs no text call at all — it is a `render` carrying its own `prompt`.

Deliberately **not** `schemaVersion`-gated, for `models.py`'s reason: that number guards the
replicated graph wire and its client twin wipes replicas, and these routes add no field to any
record beyond what `POST /graph` already carries. The rows they write go through `merge_graph` and
are gated there like every other write.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import binary_body, json_body
from acervo.repository import graph
from acervo.services.images import (
    apply_settings,
    attach_picture,
    prompt_view,
    settings_view,
    suppress_prompt,
)

router = APIRouter()

# A 1024² WebP master is around 110 KiB; this is room for an unprocessed phone photograph and a
# refusal well before anything large enough to matter reaches the decoder.
PICTURE_LIMIT = 16 * 1024 * 1024


@router.get("/images/settings")
def read_settings(request: Request) -> JSONResponse:
    return data(settings_view(request.app.state.settings, owner_id(request)))


@router.put("/images/settings")
async def write_settings(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    return data(
        await run_in_threadpool(apply_settings, request.app.state.settings, owner, body)
    )


@router.put("/images/senses/{sense_id}/picture")
async def picture(sense_id: str, request: Request) -> JSONResponse:
    """The owner's own file, sent as a raw body rather than as multipart.

    One route does not justify `python-multipart` in the server image, and there is exactly one part
    to send. The device id rides in a header for the same reason — there is no form to put it in.

    Keyed by the **sense** while drawing is keyed by the prompt, and the asymmetry is deliberate:
    drawing needs a brief, so the row that holds one is the right key, while a picture that arrives
    as bytes has no brief and may be the first thing that sense ever gets. The prompt id is derived
    from the sense, so the row is found or minted at the id it was always going to have.

    `X-Acervo-Drawn-By` names the model that drew the picture originally, which makes this a
    *restore* — an import putting a bundle's `media/` back — rather than a picture the owner chose.
    The row then keeps its provenance and stays replaceable. Without it the picture is the owner's
    own: no rendering model, and left alone by anything that draws.
    """
    owner = owner_id(request)
    device = graph.require_device(request.headers.get("x-acervo-device"))
    drawn_by = (request.headers.get("x-acervo-drawn-by") or "")[:240]
    payload = await binary_body(request, PICTURE_LIMIT)
    return data(
        await run_in_threadpool(
            attach_picture, request.app.state.settings, owner, device, sense_id, payload, drawn_by
        )
    )


@router.get("/images/prompts/{prompt_id}")
def read_prompt(prompt_id: str, request: Request) -> JSONResponse:
    """The row and the prompt it composes to — which is rebuilt, never stored."""
    return data(prompt_view(owner_id(request), prompt_id))


@router.delete("/images/prompts/{prompt_id}")
async def remove(prompt_id: str, request: Request) -> JSONResponse:
    """Remove the picture and rule the sense out. Not a tombstone — see `services/images.py`."""
    owner = owner_id(request)
    device = graph.require_device(request.headers.get("x-acervo-device"))
    return data(
        await run_in_threadpool(
            suppress_prompt, request.app.state.settings, owner, device, prompt_id
        )
    )

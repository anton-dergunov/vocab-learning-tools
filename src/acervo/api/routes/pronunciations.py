"""Pronouncing what an article shows, one model call per request.

Under `/pronunciations` rather than `/speech`, which is the allow-listed proxy to the spoken-usage
corpus — recorded human speech, a different thing from a voice reading a record aloud.

- `POST /pronunciations/{collection}/{id}` answers with the clip row for one spoken field: the stored
  one while it still says what the record says, otherwise a new recording. `again` records it anew,
  which is "Record again" after hearing a bad one.
- `POST /pronunciations/utterance` reads a selection aloud and answers with the audio itself. Nothing
  is stored, because a selection names no record.
- `PUT /pronunciations/{collection}/{id}/audio` puts back a clip an export carried.

Not `schemaVersion`-gated, for `images.py`'s reason: the rows these write go through `merge_graph`
and are gated there like every other write.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import binary_body, json_body
from acervo.repository import graph
from acervo.services.pronunciations import (
    CLIP_LIMIT,
    apply_settings,
    pronounce,
    restore,
    settings_view,
    utterance,
)

router = APIRouter()


@router.get("/pronunciations/settings")
async def read_settings(request: Request) -> JSONResponse:
    owner = owner_id(request)
    return data(await run_in_threadpool(settings_view, request.app.state.settings, owner))


@router.put("/pronunciations/settings")
async def write_settings(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    return data(await run_in_threadpool(apply_settings, request.app.state.settings, owner, body))


@router.post("/pronunciations/utterance")
async def say(request: Request) -> Response:
    """The audio itself rather than a `{"data": …}` envelope: there is no record to describe."""
    owner = owner_id(request)
    body = await json_body(request)
    audio, mime, spoken = await run_in_threadpool(
        utterance, request.app.state.settings, owner, str(body.get("text") or ""), str(body.get("language") or "")
    )
    return Response(
        content=audio, media_type=mime,
        headers={"X-Acervo-Provider": spoken["provider"], "X-Acervo-Model": spoken["model"],
                 "X-Acervo-Voice": spoken["voice"], "Cache-Control": "no-store"},
    )


@router.post("/pronunciations/{collection}/{target_id}")
async def record(collection: str, target_id: str, request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    device = graph.require_device(body.get("deviceId"))
    return data(await run_in_threadpool(
        pronounce, request.app.state.settings, owner, device, collection, target_id, body.get("again") is True
    ))


@router.put("/pronunciations/{collection}/{target_id}/audio")
async def put_back(collection: str, target_id: str, request: Request) -> JSONResponse:
    """Raw bytes, with who recorded them in the query string — the text may be any script, which a
    header cannot carry, and there is exactly one part to send."""
    owner = owner_id(request)
    device = graph.require_device(request.headers.get("x-acervo-device"))
    payload = await binary_body(request, CLIP_LIMIT)
    spoken = {name: request.query_params.get(name, "") for name in ("text", "providerId", "modelId", "voice", "emotion")}
    return data(await run_in_threadpool(
        restore, request.app.state.settings, owner, device, collection, target_id, payload, spoken
    ))

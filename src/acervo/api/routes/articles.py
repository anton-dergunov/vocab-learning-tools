"""`POST /articles`: save one parsed document (`docs/architecture/server.md`, "Jobs").

The device sends the `ArticleDraft` its YAML parsed into, and the server works out what that means
for the stored entry. `POST /graph` stays for raw record writes — study states, topics, vocabularies,
the Anki consumer — and an article goes through here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import graph
from acervo.services import photo
from acervo.services.articles import save_article

router = APIRouter()


@router.post("/articles")
async def save(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    device = graph.require_device(body.get("deviceId"))
    minted = body.get("minted") or []
    if not isinstance(minted, list):
        raise ApiError(400, "invalid_input", "minted must be a list of record ids.")
    # A save enriches what it creates, unless the writer will ask later — a bundle import restoring
    # its pictures first.
    enqueue = None if body.get("enrich") is False else graph.SAVE
    return data(await run_in_threadpool(
        lambda: save_article(
            account, device, body.get("draft"), minted, enqueue=enqueue, base=body.get("base"),
            # A photo taken for this word is kept by the save that names it (`services/photo.py`).
            place_photo=photo.placer(request.app.state.settings),
        )
    ))

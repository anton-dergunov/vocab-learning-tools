"""Settings ▸ Rules: the owner's standing rules for everything a text model writes for them."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.services.rules import apply_settings, settings_view

router = APIRouter()


@router.get("/rules")
def read(request: Request) -> JSONResponse:
    return data(settings_view(owner_id(request)))


@router.put("/rules")
async def write(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    return data(await run_in_threadpool(apply_settings, owner, body))

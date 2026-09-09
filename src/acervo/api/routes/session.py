"""Signing in, and staying signed in. Registration is closed: accounts come from `admin.py`."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api import auth
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import accounts

router = APIRouter()


def _session(secret: str, user) -> dict:
    return {
        "token": auth.mint(secret, user),
        "user": {"id": user["id"], "email": user["email"]},
    }


@router.post("/session")
async def sign_in(request: Request) -> JSONResponse:
    body = await json_body(request)
    user = await run_in_threadpool(
        accounts.authenticate, str(body.get("email") or ""), str(body.get("password") or "")
    )
    return data(_session(request.app.state.jwt_secret, user))


@router.post("/session/refresh")
def refresh(request: Request) -> JSONResponse:
    user = auth.owner(request)
    return data(_session(request.app.state.jwt_secret, user))

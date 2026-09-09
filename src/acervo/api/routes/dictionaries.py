"""What this server holds, and what it can look up on the client's behalf."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.errors import ApiError
from acervo.services.dictionaries.listing import installed
from acervo.services.dictionaries.online import SOURCES

router = APIRouter()


@router.get("/dictionaries")
def listing(request: Request) -> JSONResponse:
    owner_id(request)
    return data({"dictionaries": installed(Path(request.app.state.settings.dictionaries_path))})


@router.get("/dictionaries/online/{source}")
def online(request: Request, source: str) -> JSONResponse:
    owner_id(request)
    connector = SOURCES.get(source)
    if connector is None:
        raise ApiError(404, "not_found", "No such online dictionary.")
    word = (request.query_params.get("word") or "").strip()
    if not word:
        raise ApiError(400, "word_required", "Ask for a word.")
    language = (request.query_params.get("language") or "").strip()
    return data({"source": source, "word": word, "entries": connector(word, language)})

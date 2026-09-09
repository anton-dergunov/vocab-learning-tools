"""Capture: text in, an entry to review out.

The order of operations here is itself contract. The vocabulary checks come before generation, so an
unkept language never spends a model call; the duplicate check comes after resolve and before
compose, so a repeat capture costs one call rather than two. No transaction is held across either
model call.

The whole pipeline runs in the threadpool. Two model calls of up to 120 seconds each on the event
loop would stall every other request for four minutes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.errors import ApiError
from acervo.repository import graph
from acervo.services.capture.apply import apply_draft
from acervo.services.capture.compose import compose
from acervo.services.capture.draft import draft_from
from acervo.services.capture.resolve import resolve
from acervo.settings import Settings

router = APIRouter()

TEXT_LIMIT = 20000


def run_capture(settings: Settings, account: str, device: str, body: dict[str, Any]) -> dict[str, Any]:
    vocabularies = graph.owner_vocabularies(account)
    resolution = resolve(settings, body, vocabularies)

    vocabulary = next(
        (entry for entry in vocabularies if entry["language"] == resolution["language"]), None
    )
    if vocabulary is None:
        # Deliberately before generation: building an article for a language the owner does not keep
        # would spend a model call on something with nowhere to go.
        raise ApiError(
            409,
            "language_not_configured",
            f"This looks like {resolution['language']}, which you have no vocabulary for yet. "
            "Add it in Settings, then capture this again.",
        )
    if not vocabulary["glossLangs"]:
        raise ApiError(
            409,
            "language_not_configured",
            f"Your {resolution['language']} vocabulary has no translation language set, so an entry "
            "cannot be built. Choose one in Settings.",
        )

    duplicates = graph.duplicate_lexemes(
        account, resolution["language"], resolution["headword"], resolution["lemma"]
    )
    if duplicates:
        # Merging a repeat capture into the entry it belongs to needs the article conversation to do
        # it well. Until then, say so plainly rather than making a near-duplicate.
        return {"resolution": resolution, "duplicates": duplicates, "draft": None, "applied": None}

    topics = graph.owner_topics(account)
    # The model that answered, not the one that was asked first: with a chain, those differ the
    # moment a provider is rate limited, and the entry must record the one that did the work.
    answer, model_id = compose(settings, resolution, body, vocabulary, topics)
    draft = draft_from(answer, resolution, body, vocabulary, topics, model_id)

    applied = None
    if body.get("apply") is True:
        applied = {"lexemeId": apply_draft(account, device, draft, topics)}
    return {"resolution": resolution, "duplicates": [], "draft": draft, "applied": applied}


@router.post("/capture")
async def capture(request: Request) -> JSONResponse:
    account = owner_id(request)
    body = await json_body(request)
    graph.require_schema_version(body.get("schemaVersion"))
    device = graph.require_device(body.get("deviceId"))
    text = str(body.get("text") or "")
    if not text.strip():
        raise ApiError(400, "invalid_input", "There is nothing to capture.")
    if len(text) > TEXT_LIMIT:
        raise ApiError(400, "invalid_input", "That capture is too long to process in one request.")
    return data(await run_in_threadpool(run_capture, request.app.state.settings, account, device, body))

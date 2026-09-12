"""The allow-listed window onto the spoken-usage corpus, behind Acervo's own auth.

An **allow-list rather than a pass-through**, and the difference is the point: each route below is
written out, so a route added to the retrieval service never silently becomes an Acervo route, and
no path the browser sends is ever concatenated into a URL. The mutating channel calls are the only
ones that carry the operator token, and it is attached here rather than anywhere a client can see.

These return the corpus's own body verbatim rather than Acervo's `{"data": …}` envelope — see
`services/speech.py` for why. It is the one exception in the API and it buys the packaged typed
client working unchanged.

The allow-list is the *player's* surface, not the whole service: search and a clip for reading, the
translation job for the modal, and the channel catalogue for Settings. Anything else that service
grows — batches, suggestions, its own readiness — stays out until something here needs it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from acervo.api.auth import owner_id
from acervo.api.payload import json_body
from acervo.services.speech import Forwarded, forward

router = APIRouter()

PREFIX = "/speech"


def _answer(forwarded: Forwarded) -> Response:
    return Response(
        content=forwarded.body, status_code=forwarded.status, media_type=forwarded.media_type
    )


# ── reading, which needs no token at all ────────────────────────────────────


@router.get(f"{PREFIX}/status")
def status(request: Request) -> Response:
    owner_id(request)
    return _answer(forward(request.app.state.settings, "GET", "/status"))


@router.get(f"{PREFIX}/statistics")
def statistics(request: Request) -> Response:
    owner_id(request)
    return _answer(forward(request.app.state.settings, "GET", "/statistics"))


@router.get(f"{PREFIX}/search")
def search(request: Request) -> Response:
    """The query string is forwarded as the corpus's own parameters, which it validates itself.

    Acervo deliberately does not second-guess them: `limit`, `match_mode` and `order` are that
    service's contract, it refuses what it will not serve with a 400 naming the reason, and a second
    validator here would be one more thing to keep in step across a version pin.
    """
    owner_id(request)
    return _answer(
        forward(request.app.state.settings, "GET", "/search", params=dict(request.query_params))
    )


@router.get(f"{PREFIX}/clips/{{segment_id}}")
def clip(segment_id: str, request: Request) -> Response:
    owner_id(request)
    return _answer(forward(request.app.state.settings, "GET", f"/clips/{segment_id}"))


@router.get(f"{PREFIX}/channels")
def channels(request: Request) -> Response:
    owner_id(request)
    return _answer(
        forward(request.app.state.settings, "GET", "/channels", params=dict(request.query_params))
    )


# ── the player's target text, which Acervo stores none of ──────────────────


@router.post(f"{PREFIX}/clips/{{segment_id}}/translations")
async def request_translation(segment_id: str, request: Request) -> Response:
    """Ask the corpus to translate a clip. A job, because it is two provider calls and it caches.

    Acervo stores nothing this returns (§2.13). The article's own translation line came from the
    clip-selection call and lives in the graph; this is the richer thing — a validated word
    alignment the player renders as an interactive relation — and it is the service's, fetched when
    the modal opens and gone when it closes.

    `POST` and yet no operator token: this is not a channel mutation. It writes only that service's
    own translation cache, on behalf of a reader Acervo has already authenticated.
    """
    owner_id(request)
    body = await json_body(request)
    return _answer(
        forward(
            request.app.state.settings, "POST", f"/clips/{segment_id}/translations", json_body=body
        )
    )


@router.get(f"{PREFIX}/translations/{{job_id}}")
def translation(job_id: str, request: Request) -> Response:
    owner_id(request)
    return _answer(forward(request.app.state.settings, "GET", f"/translations/{job_id}"))


@router.delete(f"{PREFIX}/translations/{{job_id}}")
def cancel_translation(job_id: str, request: Request) -> Response:
    """Closing the dialog while a translation is still running should not leave it running."""
    owner_id(request)
    return _answer(forward(request.app.state.settings, "DELETE", f"/translations/{job_id}"))


# ── the channel catalogue, which is the corpus's and is edited through here ─


@router.post(f"{PREFIX}/channels")
async def add_channel(request: Request) -> Response:
    owner_id(request)
    body = await json_body(request)
    return _answer(
        forward(request.app.state.settings, "POST", "/channels", json_body=body, operator=True)
    )


@router.patch(f"{PREFIX}/channels/{{language}}/{{channel_id}}")
async def update_channel(language: str, channel_id: str, request: Request) -> Response:
    owner_id(request)
    body = await json_body(request)
    return _answer(
        forward(
            request.app.state.settings, "PATCH", f"/channels/{language}/{channel_id}",
            json_body=body, operator=True,
        )
    )


@router.post(f"{PREFIX}/channels/{{language}}/{{channel_id}}/enable")
def enable_channel(language: str, channel_id: str, request: Request) -> Response:
    owner_id(request)
    return _answer(
        forward(
            request.app.state.settings, "POST", f"/channels/{language}/{channel_id}/enable",
            operator=True,
        )
    )


@router.post(f"{PREFIX}/channels/{{language}}/{{channel_id}}/disable")
def disable_channel(language: str, channel_id: str, request: Request) -> Response:
    owner_id(request)
    return _answer(
        forward(
            request.app.state.settings, "POST", f"/channels/{language}/{channel_id}/disable",
            operator=True,
        )
    )

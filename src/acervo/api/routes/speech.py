"""The allow-listed window onto the spoken-usage corpus, behind Acervo's own auth.

An **allow-list rather than a pass-through**, and the difference is the point: each route below is
written out, so a route added to the retrieval service never silently becomes an Acervo route, and
no path the browser sends is ever concatenated into a URL. The mutating channel calls are the only
ones that carry the operator token, and it is attached here rather than anywhere a client can see.

These return the corpus's own body verbatim rather than Acervo's `{"data": …}` envelope — see
`services/speech.py` for why. It is the one exception in the API and it buys the packaged typed
client working unchanged.
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

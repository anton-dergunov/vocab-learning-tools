"""`GET /events`: one authenticated stream that says *something changed* (§4.8).

Two message types, `job` and `revision`, and never a record: a replica still changes only through
the cursor pull, so there is exactly one way it does. A client that loses the stream loses nothing
but latency — its 60-second pull still converges — and rebuilds its open-job map from
`GET /jobs?open=true` when it reconnects.

Server-sent events, read by the client with `fetch` rather than `EventSource`, which cannot send the
bearer header. A comment line goes out every few seconds so a proxy does not close an idle
connection and a dead one is noticed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from acervo import notify
from acervo.api.auth import owner_id

router = APIRouter()

HEARTBEAT_SECONDS = 15.0


def frame(message: dict[str, Any]) -> str:
    return f"event: {message['type']}\ndata: {json.dumps(message, separators=(',', ':'))}\n\n"


async def stream(
    owner: str,
    disconnected: Callable[[], Awaitable[bool]],
    *,
    heartbeat: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """This owner's messages as SSE frames, until the client goes away."""
    with notify.hub.subscribe(owner) as queue:
        # Said at once, so a client knows the stream is live before anything has happened — which is
        # when it should rebuild its map, and not a moment earlier.
        yield frame({"type": "ready"})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except asyncio.TimeoutError:
                if await disconnected():
                    return
                yield ": still here\n\n"
                continue
            yield frame(message)


@router.get("/events")
def events(request: Request) -> StreamingResponse:
    account = owner_id(request)
    return StreamingResponse(
        stream(account, request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            # Asks nginx-style proxies not to buffer; Tailscale Serve passes a stream as it comes.
            "X-Accel-Buffering": "no",
        },
    )

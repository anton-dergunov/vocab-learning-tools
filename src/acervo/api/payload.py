"""Reading a request body.

An unreadable body is treated as an empty one, so a malformed request fails on the field it is
missing rather than on a parser error the client has no code for.
"""

from __future__ import annotations

from fastapi import Request

from acervo.errors import ApiError


async def json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - the parse error is diagnostic, not something to report
        return {}
    return payload if isinstance(payload, dict) else {}


async def binary_body(request: Request, limit: int) -> bytes:
    """A raw request body, refused before it is held in full if it is too large.

    Read in chunks against a running total rather than awaited whole and measured afterwards: a
    `Content-Length` is what the sender claims, and the point of a limit is not to trust it.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "too_large", "That file is too large.")

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise ApiError(413, "too_large", "That file is too large.")
        chunks.append(chunk)
    if not total:
        raise ApiError(400, "invalid_input", "The request carried no file.")
    return b"".join(chunks)

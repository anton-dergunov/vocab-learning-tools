"""Reading a request body.

An unreadable body is treated as an empty one, so a malformed request fails on the field it is
missing rather than on a parser error the client has no code for.
"""

from __future__ import annotations

from fastapi import Request


async def json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - the parse error is diagnostic, not something to report
        return {}
    return payload if isinstance(payload, dict) else {}

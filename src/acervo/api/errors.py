"""The one envelope.

Every response is `{"data": …}` or `{"error": {"code", "message"}}`. The client treats *any* body
without `data` as a generic failure, so FastAPI's `{"detail": …}` must never reach it — which is what
these three handlers are for.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from acervo.errors import ApiError

logger = logging.getLogger("acervo.api")

GENERIC_FAILURE = "The Acervo server could not complete the request."


def data(payload: Any, status: int = 200) -> JSONResponse:
    return JSONResponse({"data": payload}, status_code=status)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, raised: ApiError) -> JSONResponse:
        if raised.status >= 500:
            logger.error("Acervo API request failed", exc_info=raised)
        return error(raised.status, raised.code, raised.message)

    @app.exception_handler(RequestValidationError)
    async def _invalid_input(_request: Request, raised: RequestValidationError) -> JSONResponse:
        # A malformed body is the caller's mistake and gets the code the client already handles;
        # FastAPI's own 422 with a `detail` list would read as an unexplained failure.
        return error(400, "invalid_input", "The request could not be read.")

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, raised: HTTPException) -> JSONResponse:
        if raised.status_code >= 500:
            logger.error("Acervo API request failed", exc_info=raised)
            return error(raised.status_code, "server_error", GENERIC_FAILURE)
        code = "not_found" if raised.status_code == 404 else "request_failed"
        return error(raised.status_code, code, str(raised.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, raised: Exception) -> JSONResponse:
        # An unhandled exception must not leak its internals. An error raised deliberately carries a
        # message written for the owner and is handled above.
        logger.error("Acervo API request failed", exc_info=raised)
        return error(500, "server_error", GENERIC_FAILURE)

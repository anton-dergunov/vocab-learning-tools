"""What this server is, and whether it can build entries."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo.api.errors import data
from acervo.services.llm import capture_health
from acervo.settings import SCHEMA_VERSION

router = APIRouter()


@router.get("/health")
def health(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    return data({
        "name": "Acervo",
        "version": settings.app_version,
        "build": settings.app_build,
        "schemaVersion": SCHEMA_VERSION,
        # Whether this server can build entries at all, so the app can say why the button is off
        # rather than failing at the moment someone finally uses it. Provider and model are
        # identifiers the owner chose and needs to see; the key, the endpoint and the Vertex project
        # are deployment details and stay on the server.
        "capture": capture_health(settings),
    })

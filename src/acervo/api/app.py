"""The application: routers, CORS, the error envelope, and the static surfaces."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acervo.api import auth, errors, static
from acervo.api.routes import (
    capture,
    dictionaries,
    graph,
    health,
    images,
    mac_release,
    models,
    session,
)
from acervo.repository.session import open_database
from acervo.settings import Settings
from acervo.settings import settings as read_settings

API_ROOT = "/api/acervo/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or read_settings()
    app = FastAPI(title="Acervo", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = open_database(settings.database_path)
    app.state.jwt_secret = auth.resolve_secret(settings)

    # PocketBase allowed every origin by default; FastAPI sends nothing. The macOS host loads its
    # interface from `acervo://app` and calls the server cross-origin with headers that trigger a
    # preflight, so without this every call fails inside the browser with no server-side log and the
    # client reports "The Acervo server could not be reached" — the wrong diagnosis, with no evidence
    # pointing anywhere near the truth. Credentials stay off: auth is a header, never a cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Length", "Content-Range"],
    )

    errors.install(app)

    api = APIRouter(prefix=API_ROOT)
    for module in (health, session, graph, capture, dictionaries, images, mac_release, models):
        api.include_router(module.router)
    app.include_router(api)

    # Registered last, so the two catch-alls it adds never shadow a real route.
    static.install(app)
    return app

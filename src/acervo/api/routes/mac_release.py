"""What macOS application this server is offering, if any."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo.api.errors import data

router = APIRouter()

DOWNLOAD_ROOT = "/api/acervo/downloads/"


@router.get("/mac-release")
def mac_release(request: Request) -> JSONResponse:
    """The published release, or null.

    Null is an answer, not a failure: the Mac host decodes `let data: MacRelease?`, so a release that
    has not been published yet must arrive as `{"data": null}` rather than as an error.
    """
    directory = Path(request.app.state.settings.downloads_path)
    try:
        manifest = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data(None)
    if not isinstance(manifest, dict):
        return data(None)
    fields = {key: str(manifest.get(key) or "").strip() for key in ("file", "version", "build", "sha256")}
    if not all(fields.values()):
        return data(None)
    try:
        size = int(manifest.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return data({
        "version": fields["version"],
        "build": fields["build"],
        "file": fields["file"],
        "size": size,
        "sha256": fields["sha256"],
        "url": DOWNLOAD_ROOT + quote(fields["file"], safe=""),
    })

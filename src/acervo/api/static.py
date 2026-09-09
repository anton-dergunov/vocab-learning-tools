"""The three static surfaces, and the two different auth policies among them.

Downloads are open because the macOS updater fetches them with no credentials. Dictionaries are
closed because the service worker must not precache tens of MiB and because the data is third-party
and mostly share-alike — the owner's own server handing it to the owner's own devices is not the same
thing as publishing it.

Both must answer `Range`: the dictionary reader reads artifacts by byte range, so a dictionary the
device does not hold is read over the network by the same code. There are two silent ways to lose
that — putting compression in front of these routes, which strips `Content-Length`, and hand-rolling
a `StreamingResponse` to bolt on auth, which has no Range handling at all. So: check the token in the
route, and return a `FileResponse`.

Path containment has to be re-implemented here. PocketBase's directory filesystem gave it for free.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from acervo.api.auth import account_for, bearer_token
from acervo.errors import ApiError

NOT_FOUND = ApiError(404, "not_found", "That file is not on this server.")


def within(root: Path, relative: str) -> Path:
    """The file `relative` names inside `root`, or a 404 if it names anywhere else."""
    root = root.resolve()
    try:
        candidate = (root / relative).resolve()
    except OSError:
        raise NOT_FOUND from None
    if candidate != root and root not in candidate.parents:
        raise NOT_FOUND
    if not candidate.is_file():
        raise NOT_FOUND
    return candidate


def install(app: FastAPI) -> None:
    settings = app.state.settings

    @app.get("/api/acervo/downloads/{relative:path}", include_in_schema=False)
    def downloads(relative: str) -> FileResponse:
        return FileResponse(within(Path(settings.downloads_path), relative))

    @app.get("/api/acervo/dictionaries/{relative:path}", include_in_schema=False)
    def dictionaries(request: Request, relative: str) -> FileResponse:
        account_for(app.state.jwt_secret, bearer_token(request))
        return FileResponse(within(Path(settings.dictionaries_path), relative))

    @app.get("/api/acervo/{unmatched:path}", include_in_schema=False)
    def unknown_api_route(unmatched: str) -> None:
        # Registered after every real route, so the interface's own paths never fall through to the
        # application shell and come back as HTML with a 200.
        raise ApiError(404, "not_found", "The requested Acervo API route does not exist.")

    @app.get("/{relative:path}", include_in_schema=False)
    def application(relative: str) -> FileResponse:
        root = Path(settings.web_path)
        index = root / "index.html"
        if relative:
            try:
                return FileResponse(within(root, relative))
            except ApiError:
                pass
        # An unknown path is a client-side route, not a missing file.
        if not index.is_file():
            raise NOT_FOUND
        return FileResponse(index)

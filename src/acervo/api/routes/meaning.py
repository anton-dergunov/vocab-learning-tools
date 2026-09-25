"""The meaning map of one language (docs/server.md).

`?have=` is the `version` the device already holds — the fingerprint and whether the regions are
named — and a map still current answers `{"current": true}` alone. A plain `def`, so the drawing — seconds of CPU when the vocabulary changed, nothing when it did not —
runs in the threadpool and never on the event loop. Naming the regions is a model call, so it is not
done here: a freshly drawn map with regions queues `map.name`, and the job's completion on `/events`
is how a device knows to ask again.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.repository import jobs
from acervo.services import meaning

router = APIRouter()


@router.get("/map/{language}")
def read_map(request: Request, language: str) -> JSONResponse:
    owner = owner_id(request)
    answer, drawn = meaning.current_map(
        request.app.state.settings, owner, language, have=request.query_params.get("have") or None
    )
    if drawn and answer.get("names") == "pending":
        jobs.enqueue(owner, "map.name", trigger="manual", subject_kind="language", subject_id=language,
                     input={"fingerprint": answer["fingerprint"]})
    return data(answer)

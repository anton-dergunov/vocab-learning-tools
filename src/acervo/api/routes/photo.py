"""Reading a photo for photo capture: an image in, a page of tappable words out.

The photo is the raw body rather than multipart, for the reason `PUT /images/senses/{id}/picture`
gives: one part does not justify `python-multipart` in the image. It writes no record. It does keep
the photo, pending, so that a word added from it can keep it too — `services/photo.py` says how that
stays true to "the file and the row are written by the same party".

Online-only like every write: the interface says the server is unreachable and queues nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import binary_body
from acervo.services import photo

router = APIRouter()

# A 2048 px JPEG is about 400 KB; this is room for a screenshot or an unprocessed phone photo, and a
# refusal well before anything large enough to matter reaches the decoder.
PHOTO_LIMIT = 16 * 1024 * 1024


@router.post("/photo/read")
async def read(request: Request) -> JSONResponse:
    owner = owner_id(request)
    payload = await binary_body(request, PHOTO_LIMIT)
    return data(await run_in_threadpool(photo.read, request.app.state.settings, owner, payload))


@router.post("/photo/store")
async def store(request: Request) -> JSONResponse:
    """Keep a photo pending without reading it: the square of a screenshot that was on screen."""
    owner = owner_id(request)
    payload = await binary_body(request, PHOTO_LIMIT)
    return data(await run_in_threadpool(photo.store, request.app.state.settings, owner, payload))


@router.post("/photo/warm")
def warm(request: Request) -> JSONResponse:
    """Load the sentence splitter now, because the owner has just opened the Photo tab."""
    owner_id(request)
    photo.warm()
    return data({"warming": True})

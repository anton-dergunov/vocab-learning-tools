"""Asking for a story, and reading what can be asked for.

- `POST /stories` writes the story and the words it must use, then queues the job. It takes **word
  ids**, never a query, for `loops.py`'s reason: the interface sampled them from the scope on
  screen, so choosing words by hand later is this route with a different list and no server change.
- `DELETE /stories/{id}` tombstones the story, its parts and its words, and unlinks the pictures.
  A route rather than an ordinary client write for the reason the image routes are: the pictures
  are megabytes, nothing else would ever remove them, and the rows and the files have to be
  written by the same party.
- `POST /stories/{id}/parts/{part}/audio` reads one part aloud **now** and answers with its row. It is
  the on-demand half of what the `story.audio` step does when Settings ▸ Stories records a story as
  it is made, and it is the *same* function, so a part recorded either way is indistinguishable.
  Synchronous, like `POST /pronunciations/{collection}/{id}`: a person pressed a button and is
  waiting, and the recording is worth having the moment it exists.
- `GET /stories/types` is the dialog's one round trip: the kinds of story and the styles they can
  be drawn in, together, because the choice is meaningless without the labels.

The row is written **and then** the job is queued, in that order and not atomically. If the queue
fails, the story reads as one that was asked for and never written, and Try again queues another —
which is the derived state doing its job rather than a gap.

Not `schemaVersion`-gated, for `images.py`'s reason: the rows this writes go through `merge_graph`
and are gated there like every other write.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from acervo.api.auth import owner_id
from acervo.api.errors import data
from acervo.api.payload import json_body
from acervo.repository import graph, jobs
from acervo.services.stories import create, remove, types_view
from acervo.services.story_audio import narrate_part

router = APIRouter()


@router.get("/stories/types")
async def read_types(request: Request) -> JSONResponse:
    """The kinds of story, and the styles this owner has left switched on."""
    owner = owner_id(request)
    return data(await run_in_threadpool(types_view, request.app.state.settings, owner))


@router.post("/stories")
async def make(request: Request) -> JSONResponse:
    owner = owner_id(request)
    body = await json_body(request)
    device = graph.require_device(body.get("deviceId"))

    story = await run_in_threadpool(create, request.app.state.settings, owner, device, body)
    # Nothing rides on the job's `input`: unlike a loop's music, the kind of story and its style are
    # **facts about the story** and are on its own row from the moment it is asked for. So Try again
    # reaches for the same kind and the same look by reading the row, with nothing to carry.
    queued = await run_in_threadpool(
        lambda: jobs.enqueue(owner, "story", trigger="manual", subject_kind="story",
                             subject_id=story["id"])
    )
    return data({"story": story, "job": queued}, status=202)


@router.delete("/stories/{story_id}")
async def drop(story_id: str, request: Request) -> JSONResponse:
    """Delete a story, its parts, its words and its pictures."""
    owner = owner_id(request)
    device = graph.require_device(request.headers.get("x-acervo-device"))
    return data(
        await run_in_threadpool(remove, request.app.state.settings, owner, device, story_id)
    )


@router.post("/stories/{story_id}/parts/{part_id}/audio")
async def read_aloud(story_id: str, part_id: str, request: Request) -> JSONResponse:
    """Record one part, in the voice the story is already being read in, and answer with its row."""
    owner = owner_id(request)
    body = await json_body(request)
    device = graph.require_device(body.get("deviceId"))
    return data(await run_in_threadpool(
        narrate_part, request.app.state.settings, owner, device, story_id, part_id,
    ))

"""Acervo's binding to story narration: a part in, one recording and its row out.

The other half of the split `acervo.stories.narrate` makes, and the sibling of `services/stories.py`
(the pictures) and `services/pronunciations.py` (a word). This is where it is decided *whose* voice
reads it, and it reuses what those two already answer: the chain a pair is chosen from, the way a
model's refusal is spoken, and the file-then-row write.

**A story is read in one voice.** The first part to be recorded walks the owner's chain as any
recording does, and whichever (provider, model, voice) answers is then the only one asked for every
other passage and every other part. Falling through to another provider partway through a story would
change the speaker between paragraphs, which is worse than failing. So the pin is a *chain of one*: a
refusal from it is the answer, and the job's own rests are what wait for a busy provider. The pin is
read back off the graph — the first part already recorded — and never remembered, which is what lets a
retry, a route and a job agree without coordinating.

**A part is one file made of many recordings.** A directed voice is asked for one passage at a time,
each with its own direction (`stories/narrate.py` decides where they break), and the recordings are
joined here. Because they are joined here, where every passage sits in the file is known exactly, and
the reader can mark the passage that is sounding and start from any of them without anything having
to be aligned. A clear voice reads the whole part in one call and records no passages.

Every operation is read (transaction) → calls (**no** transaction, tens of seconds of them) → write
(transaction), for `services/stories.py`'s reason.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable

from acervo.domain.ids import now_instant
from acervo.errors import ApiError
from acervo.models import journal, load_catalogue
from acervo.models.errors import ChainExhausted, ProviderError
from acervo.pronunciation import encode, speak as speaking
from acervo.repository import graph, pronunciation_settings
from acervo.services import pronunciations, stories
from acervo.services.models import refusal
from acervo.settings import Settings
from acervo.stories import narrate

NARRATE_TEMPLATE = "acervo_story_narrate"
# What tells the voice how to read a passage. Not the sentence template a word's example uses
# ("in the moment", "keep a natural pace"): this is a narrator, and the direction is a whole sentence.
SPEAK_TEMPLATE = "acervo_pronounce_story"

# The two reasons a *model's answer* is refused for being what it is rather than for the weather. A
# segmentation that fails only this way is not worth waiting for — the part is read whole instead.
UNUSABLE = frozenset({"unusable", "empty"})

Pin = tuple[str, str, "str | None"]


def narrate_story(
    settings: Settings, owner: str, device: str, story_id: str,
    gate: Callable[[], None] | None = None, progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Record the parts that have no recording yet.

    **What is missing is re-derived here rather than passed in**, for `stories.draw_pictures`'s
    reason: a run that lost its last part to a rate limit records one part and not four. `progress`
    counts over every part, so a retry carries on from what is there and the figure never runs
    backwards.
    """
    stories._story(owner, story_id)
    parts = stories._parts(owner, story_id)
    pending = [row for row in parts if not row.get("audioRef")]
    done = len(parts) - len(pending)
    if progress is not None:
        progress(done, len(parts))
    for row in pending:
        if gate is not None:
            gate()
        narrate_part(settings, owner, device, story_id, row["id"], gate=gate)
        done += 1
        if progress is not None:
            progress(done, len(parts))
    return {"recorded": len(pending), "parts": len(parts)}


def narrate_part(
    settings: Settings, owner: str, device: str, story_id: str, part_id: str,
    gate: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Record one part and answer with its row. The one pipeline for the job and for the route."""
    started = time.monotonic()
    story = stories._story(owner, story_id)
    parts = stories._parts(owner, story_id)
    part = next((row for row in parts if row["id"] == part_id), None)
    if part is None:
        raise ApiError(404, "not_found", "That part is not in this story.")
    language = story["language"]

    preferences = pronunciation_settings.settings(owner)
    order = preferences.order_for("stories")
    pin = _pin(parts, language)

    segments = _segments(settings, owner, part["text"], language, order)
    recordings: list[speaking.Spoken] = []
    for segment in segments:
        if gate is not None:
            gate()
        style = None
        if order == "expressive" and segment.direction:
            style = speaking.direction(
                stories._template(settings, SPEAK_TEMPLATE), segment.direction, language)
        spoken = pronunciations._speak(
            settings, owner, segment.text.strip(), language, order, style,
            speaking.CALLERS["stories"], lambda reason: None, preferences=preferences, pinned=pin,
        )
        if pin is None:
            answered = spoken.result.answer
            pin = (answered.provider_id, answered.model, spoken.result.voice)
        recordings.append(spoken)

    data, mime, marked = _assemble(segments, recordings)
    row = _place_and_write(settings, owner, device, story_id, part_id, data, mime, pin, marked)
    journal.outcome(
        "story-audio", False, story=story_id, part=part_id, order=order, passages=len(segments),
        pair=f"{pin[0]}:{pin[1]}" if pin else None, voice=pin[2] if pin else None,
        bytes=len(data), seconds=time.monotonic() - started,
    )
    return row


def _pin(parts: list[dict[str, Any]], language: str) -> Pin | None:
    """The voice this story is already being read in: the first recorded part's, if it can still be
    asked for. A pair that has since left the catalogue, lost its credential or stopped speaking the
    language is not one to insist on — a story then starts again with whatever answers first."""
    for part in sorted(parts, key=lambda row: row.get("position", 0)):
        if part.get("audioRef") and part.get("audioProviderId") and part.get("audioModelId"):
            pair = (part["audioProviderId"], part["audioModelId"])
            try:
                usable = speaking.speakers([pair], load_catalogue(), language)
            except ProviderError:
                usable = ()
            return (*pair, part.get("audioVoice") or None) if usable else None
    return None


def _segments(settings: Settings, owner: str, text: str, language: str, order: str) -> tuple[narrate.Segment, ...]:
    """What is said, in order, and how each is directed. Joined, always exactly `text`."""
    if order != "expressive":
        return narrate.chunks(text)
    candidates = stories._candidates(settings, owner, "text")
    stories._require(candidates, settings, owner, "text")
    narrator = narrate.Narrator(
        load_catalogue(), candidates, stories._template(settings, NARRATE_TEMPLATE))
    try:
        tiled, usage = narrator.segment(
            narrate.build_request(language_name=speaking.language_name(language), text=text))
    except ChainExhausted as exhausted:
        if set(exhausted.reasons) <= UNUSABLE:
            # Nothing was wrong with the weather: every model was asked and none could do it. The
            # part is still worth hearing, so it is read whole, in the voice's own manner.
            journal.outcome("story-narrate", True, result="unusable", reasons=",".join(exhausted.reasons))
            return narrate.chunks(text)
        raise refusal(exhausted.last, "text") from None
    except ProviderError as error:
        raise refusal(error, "text") from None
    journal.outcome(
        "story-narrate", False, passages=len(tiled.segments), dropped=tiled.dropped, filled=tiled.filled,
        model=usage["model"], seconds=usage["seconds"],
    )
    return tiled.segments


def _assemble(
    segments: tuple[narrate.Segment, ...], recordings: list[speaking.Spoken],
) -> tuple[bytes, str, list[dict[str, Any]]]:
    """One file, and where each passage is in it. One passage is the file as it came, untouched and
    unmarked: there is no other passage to tell it from."""
    try:
        if len(recordings) == 1:
            data, mime = encode.compact(recordings[0].result.data, recordings[0].result.mime)
            return data, mime, []
        joined = encode.concat([one.result.data for one in recordings])
    except encode.CannotEncode as unwritable:
        raise ApiError(500, "audio_unencodable", f"The recording could not be assembled: {unwritable}") from None
    marked = [
        # The short direction the model wrote, and only if the voice was really sent one: what
        # `Spoken.direction` holds is the whole framed instruction, and it is None when the model
        # that answered cannot take one. Recording what was asked would claim a reading nobody gave.
        {"text": segment.text, "direction": segment.direction if spoken.direction else "",
         "start": start, "end": end}
        for segment, spoken, (start, end) in zip(segments, recordings, joined.spans)
    ]
    return joined.data, joined.mime, marked


def _place_and_write(
    settings: Settings, owner: str, device: str, story_id: str, part_id: str,
    data: bytes, mime: str, pin: Pin | None, marked: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(data) > pronunciations.CLIP_LIMIT:
        raise ApiError(400, "invalid_input", "That recording is too large to keep.")
    media = Path(settings.media_path)
    reference = (f"stories/{story_id}/{part_id}-{hashlib.sha256(data).hexdigest()[:8]}"
                 f".{speaking.extension_for(mime)}")
    stories._place(media, reference, data)
    # Read again *after* the calls, which took a while: the row this replaces may have moved — a
    # picture landed, or the other of the job and the route finished first — and a write states the
    # revision it was made from.
    fresh = graph.owned_records(owner, "storyParts", [part_id]).get(part_id)
    if fresh is None or fresh.get("deleted"):
        # The story was deleted while this was being recorded; its files go with it.
        stories._discard(media, reference, keep=None)
        raise ApiError(404, "not_found", "That part is not in this story any more.")
    previous = fresh.get("audioRef")
    at = now_instant()
    try:
        graph.merge_graph(owner, device, {"storyParts": [{
            **fresh, "audioRef": reference, "audioMime": mime,
            "audioProviderId": pin[0] if pin else "", "audioModelId": pin[1] if pin else "",
            "audioVoice": (pin[2] or "") if pin else "", "audioSegments": marked,
            "editedAt": at, "editedBy": device,
        }]}, enqueue=None)
    except Exception:
        stories._discard(media, reference, keep=previous)
        raise
    stories._discard(media, previous, keep=reference)
    return graph.owned_records(owner, "storyParts", [part_id])[part_id]

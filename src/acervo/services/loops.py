"""Acervo's binding to the loop generator: words and a scope in, a track on disk and two rows out.

The other half of the split `acervo.loops` makes, and the same split `services/clips.py` makes
against `acervo.clips`. That module knows the generator's wire shape; this one knows whose words
they are, which order speaks them, where the track goes and what Acervo's API calls a failure.

**A loop is written by the server, file and rows together**, for the reason a picture and a clip are:
nobody else holds both. The file lands first, under a name carrying a digest of its bytes, and the
rows second through `graph.merge_graph` — the same write every phone makes.

**Its state is derived, and this is where that pays.** `create` writes the `loops` row with no
`audioRef` and its `loopItems` with the words but no times; the render fills both in. So a loop whose
job failed to queue, or failed outright, simply shows as never rendered and Try again queues another
— there is no status column to get out of step with what actually happened.

Every operation is read (transaction) → render (**no** transaction, minutes of it) → write
(transaction). A repository function is a transaction and owns its own session; a four-minute render
inside one would block every other request for as long as it ran.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Any

from acervo.domain.ids import is_record_id, new_record_id, now_instant
from acervo.errors import ApiError
from acervo.loops.client import Item, Loop, LoopError, LoopService, Operation
from acervo.repository import accounts, graph, pronunciation_settings
from acervo.settings import Settings
from acervo.tokens import mint_render, resolve_secret

# A loop is a handful of words, not a playlist. The generator has its own bound; this is Acervo's,
# and it is about what makes a track worth putting on rather than what the engine can survive.
MIN_WORDS = 1
MAX_WORDS = 40

# **Acervo mints the seed, rather than letting the generator mint its own.** Left to itself it uses
# `secrets.randbits(64)`, and a 64-bit integer does not survive the journey: JSON numbers are
# doubles in most readers, so anything above 2^53 loses precision on the way into the browser, and
# SQLite's INTEGER is signed. The first real render came back with one and the whole track was
# thrown away by the graph's range check — after four minutes of work, over a number.
#
# Minting it here fixes more than the range. The seed becomes a fact about the loop from the moment
# it is asked for, so Try again reproduces the same bed rather than a different one, and the value
# stored is provably the value that produced the track: the generator echoes back what it is given.
SEED_LIMIT = 2 ** 31

TRACK_LIMIT = 64 * 1024 * 1024

# Without the sample pack, fifteen of the generator's sixteen bed families name instruments that are
# loaded from its catalogue, so a render dies on `No samples cached for …` — how far it gets depends
# on which voices the seed happens to draw. §2.2 once said a pack-less server warns rather than
# refuses; that was written believing the render falls back to the synthesised palette, and it does
# not. Refusing in one second beats failing in four minutes, and this sentence says what to do.
NO_SAMPLES = (
    "This server has no sample pack, so a loop cannot be made. "
    "Install it once with ./deploy.sh --install-samples."
)

LOOP_REFUSALS: dict[str, tuple[int, str, str]] = {
    "unreachable": (502, "loops_unreachable", "The loop generator could not be reached, so nothing was made."),
    "busy": (503, "loops_busy", "The loop generator is busy; try again in a moment."),
    "refused": (502, "loops_failed", "The loop generator refused the request, so nothing was made."),
    "no_track": (502, "loops_failed", "The loop generator finished but produced no track."),
}


def configured(settings: Settings) -> bool:
    return bool(settings.lexibeat_url.strip())


def service(settings: Settings) -> LoopService:
    if not configured(settings):
        raise ApiError(
            503, "loops_unconfigured",
            "This Acervo server has no loop generator configured, so it cannot make loops.",
        )
    return LoopService(settings.lexibeat_url)


def refusal(error: LoopError) -> ApiError:
    """Acervo's wire vocabulary, **and** whatever the generator said.

    The code is ours because the interface branches on it; the sentence is largely theirs because
    only they know what went wrong. Keeping just the constant is how "No samples cached for
    'salamander'" became "The loop generator refused the request, so nothing was made." — a message
    that named nothing and left the owner with a four-minute failure and no next step.
    """
    status, code, message = LOOP_REFUSALS.get(error.code, LOOP_REFUSALS["refused"])
    said = (error.message or "").strip()
    return ApiError(status, code, f"{message} {said}"[:500].strip() if said else message)


def schema(settings: Settings) -> dict[str, Any]:
    """What the generator can be asked for, for the dialog. Its catalogues, never copied here."""
    try:
        found = service(settings).schema()
    except LoopError as error:
        raise refusal(error) from None
    return {
        "apiVersion": found.api_version,
        "engineVersion": found.engine_version,
        # False means the pinned sample bundle is not installed, or not all of it: `create` refuses
        # with `loops_no_samples` rather than render beds from whatever part of it is there.
        "productionBundle": found.production_bundle,
        "patterns": list(found.patterns),
        "families": list(found.families),
        "maxItems": min(found.max_items or MAX_WORDS, MAX_WORDS),
    }


# ── making one ──────────────────────────────────────────────────────────────


def create(settings: Settings, owner: str, device: str, body: dict[str, Any]) -> dict[str, Any]:
    """Write the loop and its words. Rendering is the job's, and it has not happened yet.

    The route takes **ids**, never a query: the interface sampled them from the scope on screen and
    the server does not re-derive that scope. Which also makes choosing words by hand the same route
    with a different list, and therefore no server change at all.
    """
    language = str(body.get("language") or "").strip()
    ids = body.get("lexemeIds")
    if not isinstance(ids, list) or not all(isinstance(one, str) for one in ids):
        raise ApiError(400, "invalid_input", "A loop is made from a list of word ids.")
    wanted = [one for one in ids if is_record_id(one)]
    if len(wanted) != len(ids) or not MIN_WORDS <= len(wanted) <= MAX_WORDS:
        raise ApiError(400, "invalid_input", f"A loop takes between {MIN_WORDS} and {MAX_WORDS} words.")
    if len(set(wanted)) != len(wanted):
        raise ApiError(400, "invalid_input", "A loop cannot teach the same word twice.")

    # Asked before anything is written, so a server without its samples refuses in a second rather
    # than writing rows, queueing a job and failing minutes later with the generator's own wording
    # about a missing `salamander`. One extra call on an operation that already takes minutes.
    offered = schema(settings)
    if not offered.get("productionBundle"):
        raise ApiError(409, "loops_no_samples", NO_SAMPLES)
    family = str(body.get("family") or "").strip()
    if family and family not in offered.get("families", []):
        raise ApiError(400, "invalid_input", f"The generator has no “{family}” music.")

    held = graph.owned_records(owner, "lexemes", wanted)
    items: list[dict[str, Any]] = []
    for identifier in wanted:
        lexeme = held.get(identifier)
        if lexeme is None or lexeme.get("deleted"):
            raise ApiError(404, "not_found", "One of those words is not in your vocabulary.")
        if language and lexeme.get("language") != language:
            raise ApiError(400, "invalid_input", "Every word in a loop is in one language.")
        language = language or str(lexeme.get("language") or "")
        gloss = (lexeme.get("primaryGloss") or "").strip()
        if not gloss:
            # Refused **by name** rather than silently dropped from the track: a loop of eleven words
            # where twelve were asked for, with nothing saying which went missing, is worse than a
            # refusal. Nothing backfills `primaryGloss`; the word is simply not eligible.
            raise ApiError(
                422, "no_primary_gloss",
                f"“{lexeme.get('headword')}” has no single term to speak, so it cannot be in a loop.",
            )
        items.append({"lexeme": lexeme, "gloss": gloss})

    loop_id = new_record_id()
    at = now_instant()
    stamp = {"ownerId": owner, "deleted": False, "createdAt": at, "editedAt": at,
             "editedBy": device, "revision": 0}
    changes = {
        "loops": [{
            "id": loop_id, "language": language,
            # Everything the render decides is empty until it has. An absent `audioRef` is the whole
            # of what "not made yet" means.
            "styleId": None, "seed": secrets.randbelow(SEED_LIMIT), "engineVersion": None,
            "bedFingerprint": None,
            "pattern": str(body.get("pattern") or "retrieval"),
            "audioRef": None, "audioMime": None, "durationSeconds": None,
            "position": graph.next_loop_position(owner, language),
            **stamp,
        }],
        "loopItems": [{
            "id": new_record_id(), "loopId": loop_id, "lexemeId": entry["lexeme"]["id"],
            "position": index,
            # What will be said, and what the render is told to say — the same strings, so the
            # caption is truthful from the moment the loop exists rather than only afterwards.
            "sourceText": str(entry["lexeme"].get("headword") or ""),
            "targetText": entry["gloss"],
            "emotion": (entry["lexeme"].get("emotion") or "").strip() or None,
            # Filled in by the render. Zero is not "the start of the track": it is "not timed yet",
            # and the loop's own empty `audioRef` is what says so.
            "startSeconds": 0.0, "sourceRevealSeconds": 0.0,
            "targetRevealSeconds": 0.0, "endSeconds": 0.0,
            **stamp,
        } for index, entry in enumerate(items)],
    }
    graph.merge_graph(owner, device, changes, enqueue=None)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


# ── rendering it ────────────────────────────────────────────────────────────


def render_request(settings: Settings, owner: str, loop_id: str) -> dict[str, Any]:
    """Everything one render needs, read in one go before any of it is sent."""
    loop = graph.owned_records(owner, "loops", [loop_id]).get(loop_id)
    if loop is None or loop.get("deleted"):
        raise ApiError(404, "not_found", "That loop is not in your vocabulary.")
    rows = sorted(
        (row for row in graph.loop_items(owner, loop_id) if not row.get("deleted")),
        key=lambda row: (row.get("position", 0), row.get("id", "")),
    )
    if not rows:
        raise ApiError(422, "empty_loop", "That loop has no words left in it.")

    vocabulary = next(
        (one for one in graph.owner_vocabularies(owner) if one["language"] == loop["language"]), None
    )
    gloss_language = (vocabulary or {}).get("glossLangs") or ["en"]
    account = accounts.by_id(owner)
    if account is None:
        raise ApiError(404, "not_found", "That account no longer exists.")
    return {
        "loop": loop,
        "items": [Item(row["sourceText"], row["targetText"], row.get("emotion") or "") for row in rows],
        "rows": rows,
        "source_language": {"code": loop["language"], "name": _language_name(loop["language"])},
        "target_language": {"code": gloss_language[0], "name": _language_name(gloss_language[0])},
        # One render, one token, audienced to the take route and good for an hour. It is the whole of
        # what the generator is given to speak with: no provider credential reaches that container.
        "token": mint_render(resolve_secret(settings), account, loop_id),
        # Which order the owner chose for loops. The generator builds its backend around this and
        # declares what that backend can do, so it has to travel with the request rather than be
        # asked for later — see `delivery`.
        "delivery": delivery(owner),
        # The loop's own seed, so the bed is reproducible and the number that comes back is one this
        # side can store. See `SEED_LIMIT`.
        "seed": int(loop.get("seed") or 0),
    }


def start(settings: Settings, request: dict[str, Any], **overrides: Any) -> Operation:
    loop = request["loop"]
    try:
        return service(settings).start(
            items=request["items"],
            source_language=request["source_language"],
            target_language=request["target_language"],
            token=request["token"],
            delivery=request["delivery"],
            pattern=loop.get("pattern") or "retrieval",
            seed=request.get("seed"),
            **overrides,
        )
    except LoopError as error:
        raise refusal(error) from None


def follow(settings: Settings, operation_id: str) -> Operation:
    try:
        return service(settings).operation(operation_id)
    except LoopError as error:
        raise refusal(error) from None


def store(settings: Settings, owner: str, device: str, loop_id: str, rendered: Loop) -> dict[str, Any]:
    """Fetch the finished track, write the file, then the rows. Nothing is re-encoded.

    The generator wrote MP3 at 128 kbps and these are those bytes exactly: re-encoding a lossy stream
    into another lossy codec adds a second generation of artifacts to save nothing, which is the rule
    `pronunciation/encode.py` already states for a clip that arrived compressed.
    """
    request = render_request(settings, owner, loop_id)
    loop, rows = request["loop"], request["rows"]
    try:
        audio, mime = service(settings).track(rendered.audio_url)
    except LoopError as error:
        raise refusal(error) from None
    if not audio or len(audio) > TRACK_LIMIT:
        raise ApiError(502, "loops_failed", "The loop generator's track could not be stored.")

    # A digest of the bytes, so a re-render is a *new* reference and a device that cached the old one
    # simply misses. That is what lets `mediaStore.ts` be a cache with no invalidation in it.
    digest = hashlib.sha256(audio).hexdigest()[:8]
    reference = f"loops/{loop['language']}/{loop_id}-{digest}.mp3"
    destination = Path(settings.media_path) / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(audio)
    os.replace(partial, destination)

    at = now_instant()
    timeline = {int(row.get("index", index)): row for index, row in enumerate(rendered.timeline)}
    changes = {
        "loops": [{
            **loop, "audioRef": reference, "audioMime": mime or "audio/mpeg",
            "durationSeconds": rendered.duration_seconds, "styleId": rendered.style_id or None,
            "seed": rendered.seed, "engineVersion": rendered.engine_version or None,
            "bedFingerprint": rendered.bed_fingerprint or None,
            "pattern": rendered.pattern or loop.get("pattern"),
            "editedAt": at, "editedBy": device,
        }],
        "loopItems": [
            {
                **row,
                "startSeconds": float(timeline.get(index, {}).get("start") or 0.0),
                "sourceRevealSeconds": float(timeline.get(index, {}).get("source_reveal") or 0.0),
                "targetRevealSeconds": float(timeline.get(index, {}).get("target_reveal") or 0.0),
                "endSeconds": float(timeline.get(index, {}).get("end") or 0.0),
                # Two numbers that say how the word repeats, so the player can mark which of the
                # pair is being said rather than only which word is being taught.
                "repeats": int(timeline.get(index, {}).get("repeats") or 0),
                "repeatSeconds": float(timeline.get(index, {}).get("repeat_seconds") or 0.0),
                "editedAt": at, "editedBy": device,
            }
            for index, row in enumerate(rows)
        ],
    }
    try:
        graph.merge_graph(owner, device, changes, enqueue=None)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    previous = loop.get("audioRef")
    if previous and previous != reference:
        Path(settings.media_path).joinpath(previous).unlink(missing_ok=True)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


def remove(settings: Settings, owner: str, device: str, loop_id: str) -> dict[str, Any]:
    """Delete a loop: its row, its words, and the track itself.

    The rows are tombstones like every other deletion, written through `merge_graph` so they are
    numbered and replicated the way a client's own write would be. The **file** is why this is a
    route rather than a client-side `repository.delete`: a track is megabytes, nothing else would
    ever remove it, and the same party has to write the row and unlink the file or one of them is a
    lie. That is the shape `DELETE /images/prompts/{id}` already has, for the same reason.

    The file goes **after** the rows land, and never before: a merge that raises must not take the
    track of a loop that still exists with it. A loop that was never rendered has no track and
    simply loses its rows.
    """
    loop = graph.owned_records(owner, "loops", [loop_id]).get(loop_id)
    if loop is None or loop.get("deleted"):
        raise ApiError(404, "not_found", "That loop is not in your vocabulary.")

    at = now_instant()
    stamp = {"deleted": True, "editedAt": at, "editedBy": device}
    rows = [row for row in graph.loop_items(owner, loop_id) if not row.get("deleted")]
    graph.merge_graph(owner, device, {
        "loops": [{**loop, **stamp}],
        "loopItems": [{**row, **stamp} for row in rows],
    }, enqueue=None)

    reference = loop.get("audioRef")
    if reference:
        # `missing_ok`: a track already gone is not a reason to refuse a deletion that has happened.
        Path(settings.media_path).joinpath(reference).unlink(missing_ok=True)
    return graph.owned_records(owner, "loops", [loop_id])[loop_id]


def delivery(owner: str) -> str:
    """Which order speaks a loop, as the owner chose it, and which travels with the render.

    The generator needs it to know whether to vary the repetitions itself or leave that to the
    director notes (§2.6), and it has no way to find out on its own: it holds no settings, no
    catalogue and no credential. Choosing the clear voice is therefore worth what it says it is —
    one recording a line rather than three — rather than three identical calls.
    """
    return pronunciation_settings.settings(owner).order_for("loops")


def _language_name(code: str) -> str:
    from acervo.pronunciation.speak import language_name

    return language_name(code)

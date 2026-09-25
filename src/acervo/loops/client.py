"""The narrow client against the LexiBeat loop service, and the only place its wire shape is read.

LexiBeat is a **separate repository and a separate service** (`docs/loops.md`
§2.1): Acervo does not hold the music engine, does not import `lexibeat`, and never opens its output
directory. It talks to one pinned `/api/v1` contract over HTTP, and the version it talks to is
`deploy/acervo/lexibeat/pin.json`.

Written by hand rather than taken from the wheel, exactly as `clips/corpus.py` is. Installing that
package to reach it would drag numpy, scipy, soundfile and pedalboard into Acervo's image to make
four HTTP requests, and it would put the renderer *inside* the process the whole design keeps it
outside of.

This module stands alone: no `acervo.settings`, no `acervo.errors`, no graph. It speaks its own
refusals and `services/loops.py` translates them, for the reason `acervo.models` decides *what kind
of thing* went wrong while `services/models.py` decides what Acervo's wire calls it.

**Nothing the service says escapes this module as a raw dict.** A pinned-version bump is one file to
read rather than a search — the rule `dictionary.ts` lives by for the artifact format.

The operation vocabulary is deliberately the corpus's: `operation_id`, `status`, `successful`,
`error`. `work/loop.py` can then be `work/corpus.py` with a different noun rather than a second way
of following a long-running thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

# A render is minutes of work, but every *request* here is small: starting one, asking after it, and
# fetching the finished track. The track is the only one that can be large.
TIMEOUT_SECONDS = 30.0
TRACK_TIMEOUT_SECONDS = 120.0


class LoopError(Exception):
    """Something the loop service did that was not an answer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Family:
    """One kind of music, with the words the generator gives a listener to choose it by."""

    id: str
    label: str
    description: str


@dataclass(frozen=True)
class Schema:
    """What this deployment of the generator can be asked for.

    The catalogues are **its**, never copied here: a family or a second pattern added in a later
    version appears in the dialog with nothing changing on this side.
    """

    api_version: str
    engine_version: str
    # Complete, not merely present: a bundle missing files renders thinner beds rather than failing.
    production_bundle: bool
    # Which bundle, from its own manifest. The generator's container looks for the one `pin.json`
    # names, so a stale volume reads as no bundle at all; this is for saying which one answered.
    bundle_version: str
    patterns: tuple[str, ...]
    # The kinds of music there are. `auto` is not one of them: it is the absence of a choice, and
    # the generator leaves it out of these for that reason.
    families: tuple[Family, ...]
    max_items: int

    @property
    def sample_free(self) -> bool:
        """No sample bundle, so only the synthesised palette is available.

        Not an error and not a refusal — the service serves perfectly well in this state, which is
        why its healthcheck asserts liveness. It is worth *saying*, because the difference is
        recorded instruments against oscillators rather than a slightly plainer bed.
        """
        return not self.production_bundle


@dataclass(frozen=True)
class Item:
    """One word of a loop, as the generator receives it."""

    source: str
    target: str
    direction: str = ""

    def to_wire(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "direction": self.direction}


@dataclass(frozen=True)
class Loop:
    """A finished render, as far as Acervo needs to know it. Exactly §2.9's two collections."""

    audio_url: str
    audio_mime: str
    duration_seconds: float
    pattern: str
    style_id: str
    seed: int
    engine_version: str
    bed_fingerprint: str
    bpm: float
    timeline: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Operation:
    """A render the service is running, as far as Acervo needs to know it."""

    id: str
    status: str
    successful: bool | None
    error: str | None
    fraction: float
    message: str
    result: Loop | None = None

    @property
    def finished(self) -> bool:
        return self.status not in ("queued", "running")


class LoopService:
    """Start a render, follow it, fetch the track. No retries, for `client.py`'s reason: a caller
    that wants them owns them, and a retry layer here would change how a job behaves without
    changing a line of the job."""

    def __init__(self, base_url: str, *, timeout: float = TIMEOUT_SECONDS,
                 http: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # The seam a test injects a fake service through, as `Corpus` takes one.
        self._http = http

    # -- requests ------------------------------------------------------------

    def schema(self) -> Schema:
        payload = self._send("GET", "/schema")
        patterns = payload.get("patterns")
        return Schema(
            api_version=_text(payload.get("api_version")),
            engine_version=_text(payload.get("engine_version")),
            production_bundle=payload.get("production_bundle") is True,
            bundle_version=_text((payload.get("bundle") or {}).get("version")),
            patterns=tuple(_text(row.get("id")) for row in patterns or [] if isinstance(row, dict)),
            families=tuple(
                Family(_text(row.get("id")), _text(row.get("label")), _text(row.get("description")))
                for row in payload.get("family_details") or [] if isinstance(row, dict)
            ),
            max_items=_int((payload.get("limits") or {}).get("max_items")),
        )

    def alive(self) -> bool:
        try:
            return _text(self._send("GET", "/health").get("status")) == "ok"
        except LoopError:
            return False

    def start(self, *, items: Iterable[Item], source_language: dict[str, str],
              target_language: dict[str, str], token: str, delivery: str,
              pattern: str = "retrieval", family: str = "auto", seed: int | None = None,
              palette: str = "hybrid") -> Operation:
        """Ask for one loop. `token` is the render-scoped credential the generator calls home with.

        It is the *whole* of what the generator is given to speak with: no provider key reaches that
        container, so a token that is absent or refused is a render with no voice rather than one
        that quietly falls back to something else.

        `delivery` goes with it because the generator cannot find it out: only this side knows which
        order the owner chose, and that is what decides whether a repetition is its own recording
        with its own director note or one recording varied there by pitch and speed.
        """
        body: dict[str, Any] = {
            "items": [item.to_wire() for item in items],
            "source_language": source_language,
            "target_language": target_language,
            "pattern": pattern,
            "family": family,
            "palette": palette,
            "speech": {"token": token, "delivery": delivery},
        }
        if seed is not None:
            body["seed"] = seed
        return _operation(self._send("POST", "/loops", body=body))

    def operation(self, operation_id: str) -> Operation:
        return _operation(self._send("GET", f"/operations/{operation_id}"))

    def cancel(self, operation_id: str) -> Operation:
        return _operation(self._send("DELETE", f"/operations/{operation_id}"))

    def track(self, audio_url: str) -> tuple[bytes, str]:
        """The finished MP3, stored exactly as it arrives. Acervo re-encodes nothing."""
        client = self._http or httpx.Client(timeout=TRACK_TIMEOUT_SECONDS)
        try:
            answer = client.get(_join(self.base_url, audio_url))
        except httpx.HTTPError as failure:
            raise LoopError("unreachable", f"The loop generator could not be reached: {failure}") from None
        if answer.status_code != 200:
            raise LoopError("no_track", _message(answer) or "That loop has no track.")
        return answer.content, answer.headers.get("content-type", "audio/mpeg").split(";")[0]

    # -- transport -----------------------------------------------------------

    def _send(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        client = self._http or httpx.Client(timeout=self.timeout)
        try:
            answer = client.request(method, self.base_url + path, json=body, timeout=self.timeout)
        except httpx.HTTPError as failure:
            raise LoopError("unreachable", f"The loop generator could not be reached: {failure}") from None
        if answer.status_code == 429:
            raise LoopError("busy", _message(answer) or "The loop generator is busy.")
        if answer.status_code >= 400:
            raise LoopError("refused", _message(answer) or f"The loop generator answered {answer.status_code}.")
        try:
            payload = answer.json()
        except ValueError:
            raise LoopError("refused", "The loop generator did not answer with JSON.") from None
        if not isinstance(payload, dict):
            raise LoopError("refused", "The loop generator did not describe what it did.")
        return payload


def _operation(payload: Any) -> Operation:
    if not isinstance(payload, dict) or not _text(payload.get("operation_id")):
        raise LoopError("refused", "The loop generator did not describe the render.")
    successful = payload.get("successful")
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    return Operation(
        id=_text(payload.get("operation_id")),
        status=_text(payload.get("status")) or "failed",
        successful=successful if isinstance(successful, bool) else None,
        error=_text(payload.get("error")) or None,
        fraction=_float(progress.get("fraction")),
        message=_text(progress.get("message")),
        result=_loop(payload.get("result")),
    )


def _loop(payload: Any) -> Loop | None:
    if not isinstance(payload, dict) or not _text(payload.get("audio_url")):
        return None
    timeline = payload.get("timeline")
    return Loop(
        audio_url=_text(payload.get("audio_url")),
        audio_mime=_text(payload.get("audio_mime")) or "audio/mpeg",
        duration_seconds=_float(payload.get("duration_seconds")),
        pattern=_text(payload.get("pattern")),
        style_id=_text(payload.get("style_id")),
        seed=_int(payload.get("seed")),
        engine_version=_text(payload.get("engine_version")),
        bed_fingerprint=_text(payload.get("bed_fingerprint")),
        bpm=_float(payload.get("bpm")),
        timeline=_timeline(timeline),
    )


def _timeline(payload: Any) -> tuple[dict[str, Any], ...]:
    """One row per word, built key by key rather than passed through.

    The service's rows carry a span for every utterance; Acervo stores two numbers instead, and this
    is where the many become the two — the one place its wire shape is read, which is the rule the
    module header states. Nothing of the service's own shape leaves here.
    """
    rows = payload if isinstance(payload, list) else []
    built: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        repeats, step = _cadence(row.get("utterances"))
        built.append({
            "index": _int(row.get("index")) if row.get("index") is not None else index,
            # What the render says it said, which the caller checks against what it asked for.
            "source": _text(row.get("source")),
            "target": _text(row.get("target")),
            "direction": _text(row.get("direction")),
            "start": _float(row.get("start")),
            "source_reveal": _float(row.get("source_reveal")),
            "target_reveal": _float(row.get("target_reveal")),
            "end": _float(row.get("end")),
            "repeats": repeats,
            "repeat_seconds": step,
        })
    return tuple(built)


def _cadence(utterances: Any) -> tuple[int, float]:
    """How many times a word's pair is said, and how far apart.

    A word is spoken, then its translation, then that pair again — so `repeats` is the number of
    source utterances, and `repeat_seconds` is the step between consecutive utterances *after* the
    first translation, which is where the even part of the pattern begins. The gap from a word to
    its own translation is the recall gap and is deliberately longer, so it is not the step and is
    already stored as `target_reveal` anyway.

    Zero for a render that reported no spans: the player then marks the first pass and nothing else,
    rather than marking the wrong thing.
    """
    rows = [row for row in utterances or [] if isinstance(row, dict)]
    if not rows:
        return 0, 0.0
    starts = sorted(_float(row.get("start")) for row in rows)
    repeats = sum(1 for row in rows if _text(row.get("role")) == "source")
    step = round(starts[2] - starts[1], 3) if len(starts) > 2 else 0.0
    return repeats, max(0.0, step)


def _message(answer: httpx.Response) -> str:
    """The generator's own error shape, which is `{"error": {"code", "message"}}`."""
    try:
        body = answer.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return _text(error.get("message")) if isinstance(error, dict) else ""


def _join(base: str, path: str) -> str:
    """A path the service gave us, resolved against its own base.

    Never concatenated from anything a *client* sent: `audio_url` comes out of an answer this module
    parsed, which is the only thing that makes joining it safe.
    """
    if path.startswith(("http://", "https://")):
        return path
    root = base[: -len("/api/v1")] if base.endswith("/api/v1") else base
    return root.rstrip("/") + "/" + path.lstrip("/")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

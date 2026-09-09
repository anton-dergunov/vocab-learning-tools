"""One row, one call, over LiteLLM.

Three functions, and each returns what it did. The chain lives next door in `chain.py`; this module
knows only how to ask one provider and how to read what came back.

Two things here are contract rather than implementation.

**The classification is type-first, then status.** `litellm.Timeout` carries status 408 and
`litellm.APIConnectionError` carries 500, so a map written on `status_code` alone would send a
timeout to "refused" — and `scripts/ingest_vocabulary_file.py` does not retry a refusal. The retry
behaviour would have changed without a line of the retry code changing, which is the specific
failure this package was asked to avoid.

**LiteLLM's own retries are switched off, twice.** `num_retries` is its loop and `max_retries` is
the provider SDK's, which LiteLLM otherwise sets to 2. `acervo.client` carries no retries for the
same reason: a retry layer inside the transport changes the behaviour of retry code that lives
somewhere else and is tested there.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Sequence

from acervo.models.catalogue import Row, base_url, key, passed
from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable, Reason
from acervo.models.redact import redactor
from acervo.models.results import Answer, AudioResult, ImageResult, TextResult

TIMEOUT_SECONDS = 120

_FENCED = re.compile(r"^```[a-zA-Z]*\s*\n([\s\S]*?)\n?```$")

# Classified by type, in this order, before any status is looked at.
_BY_TYPE: tuple[tuple[str, Reason], ...] = (
    ("Timeout", "unreachable"),
    ("APIConnectionError", "unreachable"),
    ("RateLimitError", "rate_limited"),
    ("AuthenticationError", "authentication"),
    ("PermissionDeniedError", "authentication"),
    ("NotFoundError", "configuration"),
    ("BadRequestError", "configuration"),  # after its subclasses, which are all configuration too
)


def _litellm():
    """LiteLLM, imported the first time something actually calls a model.

    Importing it at module scope would make `acervo.models.pacing` — which the file ingestion and
    the worker image both use — depend on a library neither of them calls.
    """
    import litellm

    # It prints provider request context on some error paths. Health refuses to name a key or a
    # project; stdout must not undo that.
    litellm.suppress_debug_info = True
    return litellm


def completion(**kwargs: Any) -> Any:
    """The seam. Tests replace this attribute; nothing else wraps it."""
    return _litellm().completion(**kwargs)


def image_generation(**kwargs: Any) -> Any:
    return _litellm().image_generation(**kwargs)


def speech_synthesis(**kwargs: Any) -> Any:
    return _litellm().speech(**kwargs)


_AUDIO_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"RIFF", "audio/wav"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
)


def audio_mime(data: bytes) -> str:
    """What these bytes actually are, rather than what the caller hoped.

    Gemini's speech models answer WAV and Cloudflare's Aura answers MP3, so a hardcoded type is
    wrong for one of them — and a stored clip labelled as the wrong container is a file nothing will
    play, discovered long after the call that made it.
    """
    for signature, mime in _AUDIO_SIGNATURES:
        if data.startswith(signature):
            return mime
    return "application/octet-stream"


def unfenced(text: str) -> str:
    """Models wrap JSON in ``` often enough that not handling it would be the top cause of failure."""
    value = (text or "").strip()
    fenced = _FENCED.match(value)
    return fenced.group(1).strip() if fenced else value


def classify(error: BaseException) -> tuple[Reason, int | None]:
    """What kind of thing went wrong, in this package's own vocabulary.

    Total by construction: an exception LiteLLM adds in a later version lands on `refused`, which is
    terminal. Falling through on something unrecognised would spend money on a mistake.
    """
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = None
    names = {base.__name__ for base in type(error).__mro__}
    for name, reason in _BY_TYPE:
        if name in names:
            return reason, status
    if status is not None:
        if status == 429:
            return "rate_limited", status
        if status in (401, 403):
            return "authentication", status
        if status in (400, 404):
            return "configuration", status
        if status >= 500:
            return "unavailable", status
    return "refused", status


def _raise(row: Row, model: str, error: BaseException) -> None:
    reason, status = classify(error)
    redact = redactor(row.secret_names)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(
        reason, redact(str(error)), provider_id=row.id, model=model, status=status
    ) from None


def _transport(row: Row) -> dict[str, Any]:
    """What every call to this row carries: the credential, the endpoint, and no retries."""
    settings: dict[str, Any] = {"num_retries": 0, "max_retries": 0, **passed(row)}
    if (credential := key(row)) is not None:
        settings["api_key"] = credential
    if (endpoint := base_url(row)) is not None:
        settings["api_base"] = endpoint
    return settings


def _answer(row: Row, model: str, started: float, response: Any, warnings: Sequence[str] = ()) -> Answer:
    return Answer(
        provider_id=row.id,
        model=model,
        seconds=time.monotonic() - started,
        cost_usd=_cost(response),
        warnings=tuple(warnings),
        attempts=((row.id, model),),
    )


def _cost(response: Any) -> float | None:
    """Cost is provenance, and provenance must not be able to fail a capture.

    `litellm.completion_cost()` raises for a model absent from its price table, which every
    Cloudflare `@cf/…` id and every local model is. `cost_usd` is declared optional precisely so
    that "unknown" is a legal answer.
    """
    hidden = getattr(response, "_hidden_params", None) or {}
    value = hidden.get("response_cost") if isinstance(hidden, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def text(
    prompt: str,
    *,
    row: Row,
    model: str | None = None,
    system: str | None = None,
    schema: Any | None = None,
    as_json: bool = False,
    timeout: float = TIMEOUT_SECONDS,
) -> TextResult:
    """One text call against one row.

    `model` is the one the chain chose from this row's list; without it the row's first is used.

    `as_json` asks for a JSON object without naming its shape, which is what the two capture prompts
    want: they return free-form documents, not a fixed model. `schema` names a shape and is used by
    the image and audio jobs. Either is sent as `response_format` only where the row says it is
    understood natively; where the row says `prompt`, the instruction is the prompt's job and the
    reply is parsed and validated afterwards. `parsed` is None when the reply was not readable as
    JSON — deciding whether that is an error belongs to the caller.
    """
    model = model or row.models_for("text")[0]
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})

    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
        **row.params_for("text"),
        **_transport(row),
    }
    wants_json = as_json or schema is not None
    if wants_json and row.schema_mode == "native":
        request["response_format"] = schema if schema is not None else {"type": "json_object"}

    started = time.monotonic()
    try:
        response = completion(**request)
    except Exception as error:  # noqa: BLE001 — classified, then re-raised as one of two types
        _raise(row, model, error)
        raise  # unreachable; _raise always raises

    body = unfenced(str(response.choices[0].message.content or ""))
    parsed = None
    if wants_json and body:
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
    return TextResult(text=body, parsed=parsed, answer=_answer(row, model, started, response))


def image(
    prompt: str,
    *,
    row: Row,
    model: str | None = None,
    seed: int | None = None,
    size: tuple[int, int] | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> ImageResult:
    """One image call against one row, through LiteLLM or through the row's own adapter."""
    model = model or row.models_for("image")[0]
    started = time.monotonic()
    if row.adapter.get("image"):
        from acervo.models import cloudflare

        data, mime = cloudflare.image(row, model, prompt, seed=seed, size=size, timeout=timeout)
        return ImageResult(data=data, mime=mime, answer=_answer(row, model, started, None))

    request: dict[str, Any] = {
        "prompt": prompt,
        "model": model,
        "timeout": timeout,
        **row.params_for("image"),
        **_transport(row),
    }
    # Asking for bytes rather than a URL is a per-provider fact and the row states it: OpenAI
    # answers with a URL unless told otherwise, and Vertex refuses the parameter outright
    # ("Setting `response_format` is not supported by vertex_ai"). It defaults to the answer that
    # needs no second fetch, so a row only speaks up to say it cannot take the parameter.
    image_capabilities = (row.capabilities.get("image") or {}) if isinstance(row.capabilities, dict) else {}
    if image_capabilities.get("responseFormat", "b64_json"):
        request["response_format"] = image_capabilities.get("responseFormat", "b64_json")
    if size is not None:
        request["size"] = f"{size[0]}x{size[1]}"
    if seed is not None:
        request["seed"] = seed
    try:
        response = image_generation(**request)
    except Exception as error:  # noqa: BLE001
        _raise(row, model, error)
        raise

    encoded = response.data[0].b64_json
    if not encoded:
        raise ProviderRefused(
            "refused", "the provider returned no image data", provider_id=row.id, model=model
        )
    return ImageResult(
        data=base64.b64decode(encoded), mime="image/png", answer=_answer(row, model, started, response)
    )


def speech(
    words: str,
    *,
    row: Row,
    model: str | None = None,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> AudioResult:
    """One speech call against one row.

    `style` is carried only where the row says it is understood; a row that declares
    `capabilities.audio.style` as `unsupported` drops it with a warning rather than sending an
    instruction the provider will read aloud.
    """
    model = model or row.models_for("audio")[0]
    started = time.monotonic()
    if row.adapter.get("audio"):
        from acervo.models import cloudflare

        data, _declared = cloudflare.speech(row, model, words, voice=voice, timeout=timeout)
        warnings = ("style is not supported by this provider",) if style else ()
        return AudioResult(
            data=data, mime=audio_mime(data), answer=_answer(row, model, started, None, warnings)
        )

    audio = (row.capabilities.get("audio") or {}) if isinstance(row.capabilities, dict) else {}
    request: dict[str, Any] = {
        "model": model,
        "input": words,
        # Voice names do not carry across providers: Gemini refuses OpenAI's "alloy" and names
        # twenty-nine of its own. The row says which one it means.
        "voice": voice or audio.get("defaultVoice"),
        "timeout": timeout,
        **row.params_for("audio"),
        **_transport(row),
    }
    warnings: list[str] = []
    if style:
        if audio.get("style") == "instruction":
            request["instructions"] = style
        else:
            warnings.append("style is not supported by this provider")
    try:
        response = speech_synthesis(**request)
    except Exception as error:  # noqa: BLE001
        _raise(row, model, error)
        raise

    return AudioResult(
        data=response.content,
        mime=audio_mime(response.content),
        answer=_answer(row, model, started, response, warnings),
    )

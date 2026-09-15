"""The Cloud Text-to-Speech adapter: Google's own speech API, which LiteLLM does not reach.

One route, `text:synthesize`, serves two quite different families of voice, and the row says which
is which rather than this module:

- **Standard and WaveNet voices** exist per language, carry the language in their name
  (`es-ES-Wavenet-F`) and take no direction at all. These are the character-metered voices with the
  large free allowance, and they are what reads a headword.
- **Gemini voices** are named once (`Kore`) and speak any language. They are selected by
  `voice.modelName`, and they take a free-text delivery direction in `input.prompt` — a field of its
  own, so an example's emotion shapes the reading without ever being read out.

Authentication is Google's application default credentials, exactly as for the `vertex` row: a user
login on a workstation, a mounted service-account key on a server. Cloud TTS additionally refuses a
user login that names no quota project, so the project travels as `x-goog-user-project` whenever the
row passes one. The token is fetched once and refreshed when it lapses; it never appears in an error.

Failures go through `call.classify`, the same table every other provider's do, so a Google 429 is the
same kind of thing to the chain as a Cloudflare one.
"""

from __future__ import annotations

import base64
import json
import threading
from typing import Any

import httpx

from acervo.models.catalogue import Row, passed
from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable
from acervo.models.redact import redactor

SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DETAIL_LIMIT = 2000

_lock = threading.Lock()
_credentials: Any = None


def speech(
    row: Row,
    model: str,
    words: str,
    *,
    language: str,
    voice: str | None = None,
    style: str | None = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    declared = row.audio_for(model)
    chosen = voice or next(iter(row.voices_for(model, language)), None)
    if not chosen:
        raise ProviderRefused(
            "configuration", f"{model} names no voice for {language}", provider_id=row.id, model=model
        )
    body: dict[str, Any] = {
        "input": {"text": words},
        "voice": {"languageCode": row.locale_for(model, language), "name": chosen},
        "audioConfig": {"audioEncoding": str(row.params_for("audio").get("audioEncoding") or "MP3")},
    }
    if declared.get("modelName"):
        body["voice"]["modelName"] = declared["modelName"]
    if style:
        body["input"]["prompt"] = style

    project = passed(row).get("quotaProject")
    headers = {"Authorization": f"Bearer {_token(row, model, project)}", "Content-Type": "application/json"}
    if project:
        headers["x-goog-user-project"] = project
    try:
        response = httpx.post(SYNTHESIZE_URL, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException as error:
        _fail(row, model, "unreachable", f"timed out: {error}", None)
    except httpx.HTTPError as error:
        _fail(row, model, "unreachable", str(error), None)

    if not response.is_success:
        _fail(row, model, None, _detail(response), response.status_code)
    try:
        encoded = response.json().get("audioContent")
    except (ValueError, AttributeError):
        encoded = None
    if not isinstance(encoded, str) or not encoded:
        _fail(row, model, "empty", "the response contained no audio", response.status_code)
    return base64.b64decode(encoded), "audio/mpeg"


def _token(row: Row, model: str, project: str | None) -> str:
    """A current access token from application default credentials, refreshed only when it lapses."""
    global _credentials
    try:
        import google.auth
        import google.auth.exceptions
        import google.auth.transport.requests
    except ImportError as error:  # pragma: no cover — google-auth is a declared dependency
        raise ProviderRefused("unconfigured", str(error), provider_id=row.id, model=model) from None

    with _lock:
        try:
            if _credentials is None:
                _credentials, _ = google.auth.default(scopes=[SCOPE], quota_project_id=project)
            if not _credentials.valid:
                _credentials.refresh(google.auth.transport.requests.Request())
        except google.auth.exceptions.DefaultCredentialsError as error:
            _credentials = None
            _fail(row, model, "unconfigured", str(error), None)
        except google.auth.exceptions.RefreshError as error:
            _credentials = None
            _fail(row, model, "authentication", str(error), None)
        except google.auth.exceptions.TransportError as error:
            _fail(row, model, "unreachable", str(error), None)
        return str(_credentials.token)


def forget_credentials() -> None:
    """Drop the cached credentials, so the next call reads them again. Tests use it."""
    global _credentials
    with _lock:
        _credentials = None


def _detail(response: httpx.Response) -> str:
    """Google's own error message, which names the missing API or quota project precisely."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        return (message or json.dumps(payload, ensure_ascii=False))[:DETAIL_LIMIT]
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or "empty response body"


def _fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> None:
    from acervo.models.call import classify

    if reason is None:
        reason, _ = classify(_Status(status))
    redact = redactor(row.secret_names)
    failure = ProviderUnavailable if reason in RETRYABLE else ProviderRefused
    raise failure(reason, redact(detail), provider_id=row.id, model=model, status=status)


class _Status(Exception):
    """A bare HTTP status, so it goes through the same classifier LiteLLM's exceptions do."""

    def __init__(self, status: int | None) -> None:
        super().__init__(str(status))
        self.status_code = status

"""Google's own APIs, reached by hand: one access token, and one way to fail.

Cloud Text-to-Speech and Cloud Vision are both outside LiteLLM, and both authenticate the way the
`vertex` row does — application default credentials: a user login on a workstation, a mounted
service-account key on a server. They share this module rather than a copy each, so there is one
credential cache, one refresh, and one table from a `google.auth` exception to this package's
reasons.

A user login is refused by these APIs unless it names a quota project, so the project travels as
`x-goog-user-project` whenever the row passes one — `headers` adds it. The token is fetched once and
refreshed when it lapses; it never appears in an error.
"""

from __future__ import annotations

import json
import threading
from typing import Any, NoReturn

import httpx

from acervo.models.catalogue import Row, passed
from acervo.models.errors import RETRYABLE, ProviderRefused, ProviderUnavailable
from acervo.models.redact import redactor

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DETAIL_LIMIT = 2000

_lock = threading.Lock()
_credentials: Any = None


def headers(row: Row, model: str) -> dict[str, str]:
    """What every call to a Google API carries: a current token, and the quota project if any."""
    project = passed(row).get("quotaProject")
    found = {"Authorization": f"Bearer {token(row, model, project)}", "Content-Type": "application/json"}
    if project:
        found["x-goog-user-project"] = project
    return found


def token(row: Row, model: str, project: str | None) -> str:
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
            fail(row, model, "unconfigured", str(error), None)
        except google.auth.exceptions.RefreshError as error:
            _credentials = None
            fail(row, model, "authentication", str(error), None)
        except google.auth.exceptions.TransportError as error:
            fail(row, model, "unreachable", str(error), None)
        return str(_credentials.token)


def forget_credentials() -> None:
    """Drop the cached credentials, so the next call reads them again. Tests use it."""
    global _credentials
    with _lock:
        _credentials = None


def post(row: Row, model: str, url: str, body: dict[str, Any], timeout: float) -> httpx.Response:
    """One authenticated POST, with a transport failure already classified. A non-2xx is failed too."""
    try:
        response = httpx.post(url, headers=headers(row, model), json=body, timeout=timeout)
    except httpx.TimeoutException as error:
        fail(row, model, "unreachable", f"timed out: {error}", None)
    except httpx.HTTPError as error:
        fail(row, model, "unreachable", str(error), None)
    if not response.is_success:
        fail(row, model, None, detail(response), response.status_code)
    return response


def detail(response: httpx.Response) -> str:
    """Google's own error message, which names the missing API or quota project precisely."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        return (message or json.dumps(payload, ensure_ascii=False))[:DETAIL_LIMIT]
    except ValueError:
        return (response.text or "").strip()[:DETAIL_LIMIT] or "empty response body"


def fail(row: Row, model: str, reason: str | None, detail: str, status: int | None) -> NoReturn:
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

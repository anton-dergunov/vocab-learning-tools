"""The one place a language model is called from the request path.

A faithful port of the hook's `llmJson`, and deliberately not an abstraction: the roadmap replaces
this wholesale with `acervo.models`, and until something proves otherwise a provider is a row of data
rather than a class.

The HTTP-status to error-code mapping below is a **contract, not an implementation detail**.
`scripts/ingest_vocabulary_file.py` retries on exactly `llm_rate_limited`, `llm_unavailable` and
`llm_unreachable`, so an SDK whose exception hierarchy replaces this mapping changes the retry
behaviour without changing a line of the retry code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from acervo.errors import ApiError
from acervo.settings import Settings

TIMEOUT_SECONDS = 120
PROVIDERS = ("gemini", "vertex")

_FENCED = re.compile(r"^```[a-zA-Z]*\s*\n([\s\S]*?)\n?```$")


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    key: str
    model: str
    gemini_endpoint: str
    project: str
    location: str
    reason: str | None


def llm_reason(provider: str, key: str, project: str) -> str | None:
    """The first unmet requirement, or None when the configuration can work.

    `llm_json` re-checks these same three conditions rather than reading this, and that is
    deliberate: each one raises a *different* error code there, and the file ingestion retries on
    exactly three codes. This is the reporting view of those facts, not a second gate.

    `ACERVO_VERTEX_LOCATION` can never be the reason: it defaults to `global`.
    """
    if provider not in PROVIDERS:
        return f"ACERVO_LLM_PROVIDER is not one of {', '.join(PROVIDERS)}"
    if not key:
        return "VERTEX_API_KEY is not set" if provider == "vertex" else "GEMINI_API_KEY is not set"
    if provider == "vertex" and not project:
        return "ACERVO_VERTEX_PROJECT is not set"
    return None


def llm_settings(settings: Settings) -> LlmSettings:
    provider = settings.llm_provider.strip() or "gemini"
    key = (settings.vertex_api_key if provider == "vertex" else settings.gemini_api_key).strip()
    project = settings.vertex_project.strip()
    return LlmSettings(
        provider=provider,
        key=key,
        model=settings.llm_model.strip(),
        gemini_endpoint=settings.llm_endpoint.strip(),
        project=project,
        location=settings.vertex_location.strip() or "global",
        reason=llm_reason(provider, key, project),
    )


def capture_health(settings: Settings) -> dict[str, Any]:
    """What health says about capture. Never a key, an endpoint or a project id.

    `reason` exists because a bare "capture is unavailable" is what let a real outage stay invisible:
    false could equally mean no key, the wrong key name, a missing Vertex project or an unknown
    provider, and nobody could tell which without shell access to the server. It names the first unmet
    requirement as an environment variable, and deliberately never carries a value — health serves it
    unauthenticated.
    """
    resolved = llm_settings(settings)
    return {
        "available": resolved.reason is None,
        "provider": resolved.provider,
        "model": resolved.model,
        "reason": resolved.reason,
    }


def unfenced(text: str) -> str:
    """Models wrap JSON in ``` often enough that not handling it would be the top cause of failure."""
    value = (text or "").strip()
    fenced = _FENCED.match(value)
    return fenced.group(1).strip() if fenced else value


def _endpoint(resolved: LlmSettings) -> str:
    if resolved.provider == "vertex":
        return (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{quote(resolved.project, safe='')}/locations/{quote(resolved.location, safe='')}"
            f"/publishers/google/models/{quote(resolved.model, safe='')}:generateContent"
        )
    return (
        f"{resolved.gemini_endpoint.rstrip('/')}/v1beta/models/"
        f"{quote(resolved.model, safe='')}:generateContent"
    )


def _classify(status: int) -> ApiError:
    if status in (401, 403):
        return ApiError(
            503, "llm_authentication", "The language model credential was rejected, so nothing was created."
        )
    if status in (400, 404):
        return ApiError(
            503, "llm_configuration", "The language model configuration was rejected, so nothing was created."
        )
    if status == 429:
        return ApiError(
            503, "llm_rate_limited", "The language model is temporarily rate limited, so nothing was created."
        )
    if status >= 500:
        return ApiError(
            503, "llm_unavailable", "The language model is temporarily unavailable, so nothing was created."
        )
    return ApiError(502, "llm_failed", "The language model refused the request, so nothing was created.")


def llm_json(settings: Settings, system: str, user: str) -> Any:
    """One constrained call: pass text, get JSON back, or a code saying why not."""
    resolved = llm_settings(settings)
    if resolved.provider not in PROVIDERS:
        raise ApiError(
            503,
            "llm_configuration",
            "This Acervo server has an invalid language model provider configured, so it cannot "
            "build entries.",
        )
    if not resolved.key:
        raise ApiError(
            503,
            "capture_unavailable",
            "This Acervo server has no language model configured, so it cannot build entries.",
        )
    if resolved.provider == "vertex" and (not resolved.project or not resolved.location):
        raise ApiError(
            503,
            "llm_configuration",
            "This Acervo server is missing its Vertex project or location, so it cannot build entries.",
        )

    vertex = resolved.provider == "vertex"
    generation: dict[str, Any] = {"responseMimeType": "application/json"}
    if vertex:
        generation["thinkingConfig"] = {"thinkingLevel": "MEDIUM"}
    else:
        generation["temperature"] = 0.2

    try:
        response = httpx.post(
            _endpoint(resolved),
            headers={"content-type": "application/json", "x-goog-api-key": resolved.key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        raise ApiError(
            502, "llm_unreachable", "The language model could not be reached, so nothing was created."
        ) from None

    if not 200 <= response.status_code < 300:
        raise _classify(response.status_code)

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    candidates = (payload or {}).get("candidates") or []
    parts = ((candidates[0] if candidates else {}).get("content") or {}).get("parts") or []
    text = ""
    for part in parts:
        # Hidden reasoning is not the answer, and on some models it arrives first.
        if not part.get("thought") and str(part.get("text") or "").strip():
            text = str(part["text"])
            break
    if not text.strip():
        raise ApiError(502, "llm_empty", "The language model returned nothing, so nothing was created.")
    try:
        return json.loads(unfenced(text))
    except ValueError:
        raise ApiError(
            502, "llm_unusable", "The language model did not return a usable answer, so nothing was created."
        ) from None

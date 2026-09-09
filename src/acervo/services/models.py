"""Acervo's binding to the provider package: `Settings` in, `llm_*` error codes out.

Not to be confused with `acervo.models`, which is the provider package itself and knows nothing
about Acervo. This module is the other half of that split, and the split is deliberate:

- `acervo.models` decides **what kind of thing went wrong** — a closed seven-value `Reason`.
- This module decides **what Acervo's API calls that** — the table below.

`llm_rate_limited` and its siblings carry Acervo's HTTP statuses and prose written for the owner, so
they do not belong in a package meant to stand alone; conversely, "429 means try the next one" is
provider knowledge and does not belong in every caller. The table is the seam.

**The mapping is a contract, not an implementation detail.** `scripts/ingest_vocabulary_file.py`
retries on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`. A change here
changes the retry behaviour without changing a line of the retry code.
"""

from __future__ import annotations

from typing import Any

from acervo.errors import ApiError
from acervo.models import ChainExhausted, ProviderError, TextResult, chain, load_catalogue
from acervo.models import call as provider
from acervo.settings import Settings

# reason -> (status, code, what the owner is told). Total over `acervo.models.Reason`; the test that
# pairs every reason with a row here is what stops an eighth reason arriving unmapped.
REFUSALS: dict[str, tuple[int, str, str]] = {
    "unconfigured": (
        503,
        "capture_unavailable",
        "This Acervo server has no language model configured, so it cannot build entries.",
    ),
    "authentication": (
        503,
        "llm_authentication",
        "The language model credential was rejected, so nothing was created.",
    ),
    "configuration": (
        503,
        "llm_configuration",
        "The language model configuration was rejected, so nothing was created.",
    ),
    "rate_limited": (
        503,
        "llm_rate_limited",
        "The language model is temporarily rate limited, so nothing was created.",
    ),
    "unavailable": (
        503,
        "llm_unavailable",
        "The language model is temporarily unavailable, so nothing was created.",
    ),
    "unreachable": (
        502,
        "llm_unreachable",
        "The language model could not be reached, so nothing was created.",
    ),
    "refused": (502, "llm_failed", "The language model refused the request, so nothing was created."),
}


def chain_for(settings: Settings, kind: str = "text") -> list[str]:
    """The row ids this deployment asks, in order. Empty means "every credentialed row".

    Read per call rather than cached, for the reason `settings.py` gives: health must report what
    the server is configured with *now*, and plan 03 will replace this with an owner record that
    changes between two requests to the same process.
    """
    return [part.strip() for part in (settings.text_chain or "").split(",") if part.strip()]


def capture_health(settings: Settings) -> dict[str, Any]:
    """What health says about capture. Never a key, an endpoint or a project id.

    `reason` exists because a bare "capture is unavailable" is what let a real outage stay invisible:
    false could equally mean no key, the wrong key name, a missing Vertex project or an unknown
    provider, and nobody could tell which without shell access to the server. It names the first
    unmet requirement as an environment variable, and deliberately never carries a value — health
    serves it unauthenticated.

    `provider` and `model` name the row that would be asked *first*. Which row actually answers is
    only known after a call, and that is what lands in `modelId`.
    """
    catalogue = load_catalogue()
    ids = chain_for(settings)
    try:
        rows = chain.resolve("text", ids, catalogue)
    except ProviderError as error:
        return {"available": False, "provider": None, "model": None, "reason": error.detail}
    if not rows:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "reason": chain.unconfigured("text", ids, catalogue).detail,
        }
    return {
        "available": True,
        "provider": rows[0].id,
        "model": rows[0].model_for("text"),
        "reason": None,
    }


def llm_json(settings: Settings, system: str, user: str) -> tuple[Any, str]:
    """One constrained call: pass text, get JSON and the model that produced it, or a code saying why not.

    Returning the model is not decoration. The locked contract is that the entry records the model
    that *answered*, and under a chain that is not knowable before the call.
    """
    try:
        result: TextResult = chain.walk(
            "text",
            chain_for(settings),
            load_catalogue(),
            lambda row: provider.text(user, row=row, system=system, as_json=True),
            chain.stamped,
        )
    except ChainExhausted as exhausted:
        raise _refusal(exhausted.last) from None
    except ProviderError as error:
        raise _refusal(error) from None

    if not result.text.strip():
        raise ApiError(502, "llm_empty", "The language model returned nothing, so nothing was created.")
    if result.parsed is None:
        # A `prompt`-tier row is not sent a response format at all, so an unparseable reply is the
        # expected failure there rather than a surprise.
        raise ApiError(
            502, "llm_unusable", "The language model did not return a usable answer, so nothing was created."
        )
    return result.parsed, result.answer.model


def _refusal(error: ProviderError) -> ApiError:
    status, code, message = REFUSALS[error.reason]
    return ApiError(status, code, message)

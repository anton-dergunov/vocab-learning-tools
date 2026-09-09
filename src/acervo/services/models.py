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
from acervo.models.catalogue import Catalogue, Row, available, reason, usage_url
from acervo.repository import model_selection
from acervo.settings import Settings

KINDS = ("text", "image", "audio")

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


def deployment_chain(settings: Settings, kind: str = "text") -> list[chain.Choice]:
    """The row ids this *deployment* asks for a kind. Empty means "every credentialed row".

    Ids, never pairs: a deploy-time flag pins a provider and leaves the models to the catalogue,
    which is all it should decide. Only text has one — plans 05 and 06 are where image and audio get
    a caller, and two variables with no reader would be two more names for `install.sh` and
    `--configure-llm` to keep in step for nothing.
    """
    named = settings.text_chain if kind == "text" else ""
    return [part.strip() for part in (named or "").split(",") if part.strip()]


def chain_for(settings: Settings, owner: str | None, kind: str = "text") -> list[chain.Choice]:
    """The chain this request walks: the owner's choice, then the deployment's, then the catalogue.

    Read per call and never cached — that is what makes a change in Settings ▸ Models take effect on
    the next capture with nothing restarted. It is one indexed read against a local SQLite file, set
    against two model calls of up to 120 seconds each, so do not cache it.

    Pairs come back from the owner's record and ids from the environment; `chain.resolve` takes
    both, which is exactly why `chain.Choice` is a union.
    """
    if owner is not None:
        chosen = model_selection.chains(owner).get(kind)
        if chosen:
            return list(chosen)
    return deployment_chain(settings, kind)


def chain_readout(settings: Settings, owner: str | None, kind: str = "text") -> dict[str, Any]:
    """Which pair would be asked first for this kind, and why none can be.

    One producer, two readers: `/health` and `GET /models` both answer "can this build entries", and
    two separate computations of that would drift. Never a key, an endpoint or a project id.

    `reason` exists because a bare "capture is unavailable" is what let a real outage stay invisible:
    false could equally mean no key, the wrong key name, a missing Vertex project or an unknown
    provider, and nobody could tell which without shell access to the server. It names the first
    unmet requirement as an environment variable, and deliberately never carries a value — health
    serves it unauthenticated.

    `provider` and `model` name the pair that would be asked *first*. Which pair actually answers is
    only known after a call, and that is what lands in `modelId`.
    """
    catalogue = load_catalogue()
    chosen = chain_for(settings, owner, kind)
    try:
        candidates = chain.resolve(kind, chosen, catalogue)
    except ProviderError as error:
        return {"available": False, "provider": None, "model": None, "reason": error.detail}
    if not candidates:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "reason": chain.unconfigured(kind, chosen, catalogue).detail,
        }
    return {
        "available": True,
        "provider": candidates[0].row.id,
        "model": candidates[0].model,
        "reason": None,
    }


def capture_health(settings: Settings) -> dict[str, Any]:
    """What `/health` says about capture — this *server's* answer, deliberately owner-independent.

    `/health` is the container's liveness probe and the readout shown before anyone signs in, so it
    has no owner to read and must not grow one: an unauthenticated body that varied by caller would
    be wrong behind any cache and would put owner state on an open route. What the *owner's* chain
    will do is `GET /models`, which is also where the provider line moved to in Settings.
    """
    return chain_readout(settings, None, "text")


def llm_json(settings: Settings, owner: str | None, system: str, user: str) -> tuple[Any, str]:
    """One constrained call: pass text, get JSON and the model that produced it, or a code saying why not.

    Returning the model is not decoration. The locked contract is that the entry records the model
    that *answered*, and under a chain that is not knowable before the call.

    `owner` is required and has no default, so an omitted argument is a loud `TypeError` at the call
    site rather than a silent fall back to the deployment default. It is an owner id and never a
    chain: a caller that could assert a chain of its own would be the "an iOS Shortcut must not pick
    a model" non-goal reappearing one layer down.
    """
    try:
        result: TextResult = chain.walk(
            "text",
            chain_for(settings, owner),
            load_catalogue(),
            lambda candidate: provider.text(
                user, row=candidate.row, model=candidate.model, system=system, as_json=True
            ),
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


# ── what the owner is shown, and what they may choose ───────────────────────
# The catalogue as the interface sees it, and the one place a submitted chain is held to it. The
# repository stores what it is given and deliberately knows nothing about providers, so this is the
# only validator; `chain.resolve` checks the same things in the same order at walk time, and the two
# agreeing about which mistake is reported is what makes the refusal codes worth reading.


def _provider_view(row: Row) -> dict[str, Any]:
    """One row, as the interface needs it. Never a key, a base URL, or what the row `requires`.

    `usageUrl` is the exception that is not one: it interpolates a `requires` value — Cloudflare's
    account id — and that is the point of it. This route is authenticated and serves it to the owner
    whose account it is, and `catalogue._validate` already refuses a row that puts its *key* in
    either URL.
    """
    return {
        "id": row.id,
        "label": row.label,
        "kinds": list(row.kinds),
        "models": {kind: list(row.models_for(kind)) for kind in row.kinds},
        "available": available(row),
        "reason": reason(row),
        "usageUrl": usage_url(row),
        "notes": row.notes,
    }


def _chain_view(settings: Settings, owner: str, kind: str, catalogue: Catalogue) -> dict[str, Any]:
    """One kind's chain: whose it is, what is in it, and why nothing in it can be asked.

    `pairs` is what is *stored*, not what will be walked. An uncredentialed pair keeps its place, so
    a rotated key does not quietly destroy an ordering the owner chose; `providers[].available` is
    how the interface shows that pair will be skipped.

    `reason` comes from `chain_readout`, the same producer `/health` uses, so this route is total: a
    mistyped `ACERVO_TEXT_CHAIN` renders a reason rather than failing the settings pane.
    """
    chosen = model_selection.chains(owner).get(kind)
    if chosen:
        pairs = [{"provider": provider, "model": model} for provider, model in chosen]
        source = "owner"
    else:
        source = "deployment"
        try:
            pairs = [
                {"provider": candidate.row.id, "model": candidate.model}
                for candidate in chain.resolve(kind, deployment_chain(settings, kind), catalogue)
            ]
        except ProviderError:
            pairs = []
    return {"source": source, "reason": chain_readout(settings, owner, kind)["reason"], "pairs": pairs}


def catalogue_view(settings: Settings, owner: str) -> dict[str, Any]:
    """Everything Settings ▸ Models renders: the catalogue, and this owner's chains."""
    catalogue = load_catalogue()
    return {
        "providers": [_provider_view(row) for row in catalogue],
        "chains": {kind: _chain_view(settings, owner, kind, catalogue) for kind in KINDS},
    }


def _submitted(kind: str, value: Any, catalogue: Catalogue) -> list[tuple[str, str]]:
    """One kind's submitted chain, checked against the catalogue.

    The order of checks matches `chain.resolve`'s, so the mistake reported here is the mistake that
    would be reported at capture time. There is deliberately no availability check: a chain is an
    owner preference and a credential is deployment state, and refusing an uncredentialed pair would
    mean a rotated key locked the owner out of reordering that kind at all. `chain.resolve` skips it
    when walking, and the interface marks it.
    """
    if not isinstance(value, list):
        raise ApiError(400, "invalid_input", f"The {kind} chain must be a list of providers.")
    if not value:
        raise ApiError(
            400, "empty_chain", f"Choose at least one model for {kind}, or leave it to the server."
        )
    pairs: list[tuple[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ApiError(400, "invalid_input", f"Every {kind} entry needs a provider and a model.")
        identifier = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not identifier or not model:
            raise ApiError(400, "invalid_input", f"Every {kind} entry needs a provider and a model.")
        try:
            row = catalogue.find(identifier)
        except KeyError:
            raise ApiError(
                400, "unknown_provider", f"This server has no provider called {identifier}."
            ) from None
        if not row.serves(kind):
            raise ApiError(400, "unsupported_kind", f"{row.label} does not do {kind}.")
        if model not in row.models_for(kind):
            raise ApiError(
                400, "unknown_model", f"{row.label} does not offer {model} for {kind}."
            )
        if (identifier, model) in pairs:
            raise ApiError(400, "duplicate_pair", f"{model} is listed twice for {kind}.")
        pairs.append((identifier, model))
    return pairs


def apply_selection(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """Store the chains this request names, then answer with what `GET /models` would say.

    Every kind is validated before anything is written, so a bad second kind cannot leave the first
    one stored. Answering with the full view rather than an acknowledgement means the interface
    renders the server's answer instead of its own optimism, and gets fresh availability without a
    second round trip.
    """
    submitted = body.get("chains")
    if not isinstance(submitted, dict) or not submitted:
        raise ApiError(400, "invalid_input", "Say which chains to change.")

    catalogue = load_catalogue()
    changes: dict[str, list[tuple[str, str]] | None] = {}
    for kind, value in submitted.items():
        if kind not in KINDS:
            raise ApiError(400, "unsupported_kind", f"There is no {kind} chain.")
        # `null` forgets a kind and returns it to the deployment default. Without it, once an owner
        # has chosen there is no way back — unchecking everything is refused as an empty chain.
        changes[kind] = None if value is None else _submitted(kind, value, catalogue)

    model_selection.save(owner, changes)
    return catalogue_view(settings, owner)

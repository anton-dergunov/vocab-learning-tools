"""What went wrong, in a vocabulary that knows nothing about Acervo's wire.

The split matters and is the plan's acceptance boundary. This package decides *what kind of thing*
went wrong — a closed seven-value `Reason`. `acervo.services.models` decides what Acervo's API calls
that, because `llm_rate_limited` and its siblings carry Acervo's HTTP statuses and prose written for
the owner, and shipping those into a package meant to stand alone would defeat the point.

The division that carries the locked fall-through rule is between the two exception classes, not
between reasons: `ProviderUnavailable` is retried at the next row, `ProviderRefused` never is. An
authentication failure or a rejected configuration is a mistake to fix, not a condition to route
around; falling through on it hides the mistake and spends money elsewhere.

`unusable` and `empty` are the two reasons a *caller* raises rather than `classify`, and it is retryable for the
same argument the rule rests on. A model that answers with the wrong shape has not revealed a
mistake in the deployment — it has revealed that this model cannot do this job, which is exactly
what a chain of alternatives is for. It is also the only failure the owner can do nothing about: a
key can be rotated and a project can be fixed, but "this model does not follow a schema" is a fact
about the model. Falling through records the pair in `passed_over` like any other, so nothing is
hidden; refusing outright meant a weaker head of the chain made every stronger row behind it
unreachable.
"""

from __future__ import annotations

from typing import Literal

Reason = Literal[
    "unconfigured",    # no row in the chain has its credentials
    "authentication",  # 401, 403 — the credential was rejected
    "configuration",   # 400, 404, an unknown row id, a row that cannot serve this kind
    "refused",         # any other terminal answer, including one with no status at all
    "rate_limited",    # 429
    "unavailable",     # 5xx
    "unreachable",     # a timeout or a connection failure
    "unusable",        # it answered, and the answer was not the shape the caller asked for
    "empty",           # it answered with nothing at all
]

TERMINAL: frozenset[str] = frozenset({"unconfigured", "authentication", "configuration", "refused"})
RETRYABLE: frozenset[str] = frozenset({
    "rate_limited", "unavailable", "unreachable", "unusable", "empty"
})


class ProviderError(Exception):
    """A provider did not answer, and why.

    `detail` is redacted at construction rather than at logging: a message that is only cleaned on
    its way to a log has a path that skips the cleaning, and provider errors routinely echo the
    request — including the key — back at you. This repository is public.
    """

    reason: Reason

    def __init__(
        self,
        reason: Reason,
        detail: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.provider_id = provider_id
        self.model = model
        self.status = status


class ProviderRefused(ProviderError):
    """Terminal for this row and for the chain: auth, a bad request, an unknown model.

    Never fallen through — it is a mistake to fix, not a condition to route around.
    """


class ProviderUnavailable(ProviderError):
    """Retryable at the next row: 429, 5xx, a timeout, a connection failure."""


class ChainExhausted(Exception):
    """Every (provider, model) pair was unavailable.

    Carries the last error because that is the actionable one, and because it is what preserves the
    retry contract: a chain whose final row was rate limited must still be reported as rate
    limiting, or the file ingestion stops retrying something it should retry.
    """

    def __init__(self, attempts: tuple[tuple[str, str], ...], last: ProviderUnavailable) -> None:
        listed = ", ".join(f"{provider} {model}" for provider, model in attempts)
        super().__init__(f"every provider was unavailable: {listed}")
        self.attempts = attempts
        self.last = last

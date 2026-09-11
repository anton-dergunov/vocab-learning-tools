"""One structured model call, on the owner's chain, for the retrieval service to use.

The retrieval service's two stages — translate, then align — are each "send these instructions and
this text, get this JSON schema back". That is exactly what `acervo.models.text()` does, so the
adapter is thin: walk the chain, ask for JSON, hand back the parsed payload and how long it took.

**It reports the chain, never the row that answered.** The service caches a translation under the
`provider` and `model` its provider declares, so a fall-through that changed those would miss the
cache on every retry and re-translate work already paid for. Naming the chain means a clip
translated by the second row is found again when the first row recovers, which is the behaviour the
cache exists for. That is the opposite of the rule for a *stored* record — an `Example.modelId`
names the model that did the work — and the difference is that one is provenance and the other is a
cache key.

This module imports `acervo.models` and nothing else of Acervo's, and nothing at all of the
retrieval service's.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence


class GenerationFailed(Exception):
    """A stage that did not produce a usable answer.

    `retryable` carries the one distinction the retrieval service acts on, and it is the same
    distinction `acervo.models` already draws: a provider that is busy says nothing about the
    request, while a rejected credential is a mistake to fix rather than a condition to wait out.
    `raw` is the model's own output where there was one, for the service's invalid-output path.
    """

    def __init__(self, code: str, message: str, *, retryable: bool, raw: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.raw = raw


@dataclass(frozen=True)
class Generated:
    """What one stage produced, in the shape the service's own provider responses have."""

    payload: dict[str, Any]
    latency_ms: float
    usage: dict[str, int] | None
    raw_output: str
    provider_metadata: dict[str, str] | None = None


# The service's codes, which are a smaller set than `acervo.models`'s seven reasons.
_CODES: dict[str, tuple[str, bool]] = {
    "rate_limited": ("rate_limited", True),
    "unavailable": ("temporarily_unavailable", True),
    "unreachable": ("temporarily_unavailable", True),
    "authentication": ("provider_unavailable", False),
    "configuration": ("provider_unavailable", False),
    "unconfigured": ("provider_unavailable", False),
    "refused": ("provider_unavailable", False),
}


class ChainGenerator:
    """The owner's text chain, presented as one `generate` call.

    `chain` is given rather than looked up: this runs in the speech container, which has no business
    reaching Acervo's database, so the order arrives as `ACERVO_TEXT_CHAIN` — the rule already
    stated for any work that cannot import `repository/`.
    """

    def __init__(self, chain: Sequence[str] | None, *, timeout: float = 60.0) -> None:
        self._chain = list(chain) if chain else None
        self._timeout = timeout
        self.provider, self.model = self._identity()

    def _identity(self) -> tuple[str, str]:
        """The chain's name, fixed once, because it is a cache key rather than provenance."""
        if self._chain:
            return "acervo-chain", ",".join(self._chain)
        return "acervo-chain", "deployment-default"

    def _candidates(self):
        from acervo.models import chain, load_catalogue

        return chain.resolve("text", self._chain, load_catalogue())

    def generate(self, *, instructions: str, user_text: str, schema: Any,
                 temperature: float | None = None) -> Generated:
        from acervo.models import ChainExhausted, ProviderError, call, chain, load_catalogue

        started = time.perf_counter()
        candidates = self._candidates()
        if not candidates:
            raise GenerationFailed(
                "provider_unavailable",
                "This deployment has no language model credentialed for the text chain.",
                retryable=False,
            )
        try:
            result = chain.walk(
                "text",
                [candidate.named for candidate in candidates],
                load_catalogue(),
                lambda candidate: call.text(
                    user_text, row=candidate.row, model=candidate.model,
                    system=instructions, schema=schema, timeout=self._timeout,
                ),
                chain.stamped,
            )
        except ChainExhausted as exhausted:
            raise _failed(exhausted.last) from None
        except ProviderError as error:
            raise _failed(error) from None

        if not isinstance(result.parsed, dict):
            raise GenerationFailed(
                "invalid_output", "The language model did not return a JSON object.",
                retryable=True, raw=result.text or "",
            )
        return Generated(
            payload=result.parsed,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            usage=None,
            raw_output=result.text or "",
            # What actually answered, for the service's own provenance record. Deliberately here
            # and not in `provider`/`model`, which are the cache key and must not move.
            provider_metadata={"answered_by": f"{result.answer.provider_id}:{result.answer.model}"},
        )

    async def aclose(self) -> None:
        """Nothing to close: LiteLLM owns its own connections and this holds none."""
        return None


def _failed(error: Any) -> GenerationFailed:
    code, retryable = _CODES.get(getattr(error, "reason", "refused"), ("provider_unavailable", False))
    return GenerationFailed(code, str(error) or code, retryable=retryable)

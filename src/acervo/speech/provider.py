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

**The shape is said, not sent.** The retrieval service's two prompts name no field at all — they
end with "Return only the requested structured result" and leave the shape entirely to a schema,
which is how its own native adapter works. So the schema is rendered into the instructions here,
in JSON Schema's spelling rather than Google's, and that text is the whole contract.

It is not *also* sent as a constrained schema, and that is a measured decision rather than a
stylistic one — see `AGENTS.md`, "Constrained decoding is not used". The alignment stage was the
strongest case for sending one, because its schema restricts every id to an enum of this request's
own tokens. Measured against constructed ground truth it bought no accuracy at any size it worked
at, and above roughly a hundred tokens the provider rejected the schema outright with a 400, which
this chain classifies as terminal. Saying the shape costs a few hundred tokens and works at every
size.

This module imports `acervo.models` and nothing else of Acervo's, and nothing at all of the
retrieval service's — the dialect rename is a pure dict walk that names no package.
"""

from __future__ import annotations

import json
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


# Google's GenAI dialect spells the type keywords in capitals; JSON Schema, which `acervo.models`
# speaks, spells them in lower case. Nothing else about the two differs for the shapes that arrive
# here, so this is a rename rather than a translation — and it is a no-op on a schema that was
# already JSON Schema, which is why it is applied unconditionally rather than sniffed for.
_TYPES = frozenset({"OBJECT", "ARRAY", "STRING", "NUMBER", "INTEGER", "BOOLEAN", "NULL"})


def _keyword(value: Any) -> Any:
    """One type keyword, lower-cased if it is one. An `enum`'s values are data and never reach here."""
    return value.lower() if isinstance(value, str) and value.upper() in _TYPES else value


def json_schema(value: Any) -> Any:
    """The same schema, with its type keywords in JSON Schema's spelling."""
    if isinstance(value, dict):
        renamed = {}
        for name, member in value.items():
            if name != "type":
                renamed[name] = json_schema(member)
            elif isinstance(member, list):
                renamed[name] = [_keyword(entry) for entry in member]
            else:
                renamed[name] = _keyword(member)
        return renamed
    if isinstance(value, list):
        return [json_schema(entry) for entry in value]
    return value


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
        shape = json_schema(schema)
        # The only statement of the shape there is. The retrieval service's own prompts name no
        # field — they end with "Return only the requested structured result" and leave it entirely
        # to a schema — and no schema is sent, so without this line no row could answer either of
        # these two stages at all.
        instructions = (
            f"{instructions}\n\nReturn a single JSON object, and nothing else, matching this JSON "
            f"Schema:\n{json.dumps(shape, ensure_ascii=False)}"
        )
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
                    system=instructions, as_json=True, timeout=self._timeout,
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

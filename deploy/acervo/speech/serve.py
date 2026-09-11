"""The speech container's command: the retrieval service, with Acervo's chain behind its providers.

`speech_retrieval.create_app` takes a `TranslationProvider` and a `WordAlignmentProvider` as
constructor arguments — a public entry point of that package — so the player's target text runs on
the owner's own chain without that repository gaining a LiteLLM dependency, a schema-dialect port or
an error-taxonomy mapping. It changes nothing at all (`docs/plans/spoken-clips.md` §2.13).

This file is the only place the two projects' vocabularies meet, and it is deliberately thin: the
call itself is `acervo.speech.provider.ChainGenerator`, which imports nothing of this service's and
is tested from a virtualenv that does not carry FastAPI, uvicorn, yt-dlp or Stanza. What is here is
the wiring that knows this version's prompts, schemas and exception types.

Without `ACERVO_TEXT_CHAIN` and a credential, no providers are injected and the service falls back
to its own behaviour — the authored caption where one exists, and no target text where none does.
"""

from __future__ import annotations

import json
import os
import sys

import uvicorn

from speech_retrieval.api import create_app
from speech_retrieval.prompt_registry import (
    ALIGNMENT_PROMPT,
    TRANSLATION_PROMPT,
    TRANSLATION_SCHEMA,
    alignment_schema,
)
from speech_retrieval.settings import Settings
from speech_retrieval.translations import (
    InvalidProviderOutput,
    ProviderAlignmentRequest,
    ProviderResponse,
    ProviderTranslationRequest,
    TranslationProviderError,
)

from acervo.speech.provider import ChainGenerator, GenerationFailed


class _Stage:
    """One stage, satisfying the service's Protocol structurally.

    `provider` and `model` name the **chain**, never the row that answered: the service caches on
    them, so a fall-through that moved them would miss the cache on every retry and re-translate
    work already paid for. What actually answered travels in `provider_metadata`.
    """

    def __init__(self, generator: ChainGenerator) -> None:
        self._generator = generator
        self.provider = generator.provider
        self.model = generator.model

    def _call(self, *, instructions: str, user_text: str, schema, temperature: float) -> ProviderResponse:
        try:
            answer = self._generator.generate(
                instructions=instructions, user_text=user_text, schema=schema,
                temperature=temperature,
            )
        except GenerationFailed as failed:
            if failed.code == "invalid_output":
                raise InvalidProviderOutput(str(failed), failed.raw) from None
            raise TranslationProviderError(
                failed.code, str(failed), retryable=failed.retryable
            ) from None
        return ProviderResponse(
            payload=answer.payload,
            latency_ms=answer.latency_ms,
            usage=answer.usage,
            raw_output=answer.raw_output,
            provider_metadata=answer.provider_metadata,
        )

    async def aclose(self) -> None:
        await self._generator.aclose()


class AcervoTranslationProvider(_Stage):
    async def translate(self, request: ProviderTranslationRequest) -> ProviderResponse:
        reference = (
            "\nAuthored target-language reference (possibly free or incomplete):\n"
            + request.authored_reference
            if request.authored_reference
            else ""
        )
        return self._call(
            instructions=TRANSLATION_PROMPT.text,
            user_text=(
                f"Source language: {request.source_language}\n"
                f"Target language: {request.target_language}\n"
                f"Source text:\n{request.source_text}{reference}"
            ),
            schema=TRANSLATION_SCHEMA,
            temperature=TRANSLATION_PROMPT.temperature,
        )


class AcervoAlignmentProvider(_Stage):
    async def align(self, request: ProviderAlignmentRequest) -> ProviderResponse:
        def token_lines(tokens) -> str:
            return "\n".join(
                f"{token.id}: {json.dumps(token.text, ensure_ascii=False)}" for token in tokens
            )

        return self._call(
            instructions=ALIGNMENT_PROMPT.text,
            user_text=(
                f"Source language: {request.source_language}\n"
                f"Target language: {request.target_language}\n"
                f"Source text: {request.source_text}\n"
                f"Target text: {request.target_text}\n\n"
                f"Source tokens:\n{token_lines(request.source_tokens)}\n\n"
                f"Target tokens:\n{token_lines(request.target_tokens)}"
            ),
            schema=alignment_schema(
                [token.id for token in request.source_tokens],
                [token.id for token in request.target_tokens],
            ),
            temperature=ALIGNMENT_PROMPT.temperature,
        )


def providers():
    """Both stages, or neither.

    Separate generators so the two stages are separate cache keys — the service keys them apart and
    they need not be served by the same model. Absent when nothing is configured, which leaves the
    service's own behaviour: the authored caption where one exists, and no target text where none.
    """
    named = [part.strip() for part in os.environ.get("ACERVO_TEXT_CHAIN", "").split(",") if part.strip()]
    try:
        from acervo.models import load_catalogue
        from acervo.models.catalogue import available

        if not any(available(row) for row in load_catalogue().serving("text")):
            print("speech: no credentialed text provider; the player will show no target text",
                  file=sys.stderr, flush=True)
            return None, None
    except Exception as error:   # noqa: BLE001 — a broken catalogue must not stop the corpus serving
        # Searching and playing must keep working; only the target text is lost. Said out loud,
        # because the first version of this swallowed a misplaced catalogue and the only symptom was
        # translations quietly never appearing.
        print(f"speech: the model catalogue could not be read ({error!r}); "
              "the player will show no target text", file=sys.stderr, flush=True)
        return None, None
    return (
        AcervoTranslationProvider(ChainGenerator(named or None)),
        AcervoAlignmentProvider(ChainGenerator(named or None)),
    )


def main() -> None:
    settings = Settings.from_env()
    translation, alignment = providers()
    app = create_app(settings, translation_provider=translation, alignment_provider=alignment)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

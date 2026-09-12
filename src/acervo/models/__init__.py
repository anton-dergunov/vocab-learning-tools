"""The one way to call a model from Python: a catalogue of rows, and three functions.

Four unrelated mechanisms reached a model before this package existed, and the layer that looked
like the abstraction was dead code. What made it dead is worth stating, because it is the shape this
package is built to avoid: `ImageProvider.synthesize(text, path) -> None` had nowhere to put the
cost or the model that answered, so the pipeline that needed both bypassed it. Every function here
returns an `Answer` alongside its payload.

A provider is a row of data in `models/catalogue.json`, never a class. A row declares what it
supports — `capabilities.jsonMode` is `native` or `prompt` — and this package adapts once, at the
call boundary. There is no per-provider code except `cloudflare.py`, which exists because LiteLLM
covers neither Cloudflare images nor Cloudflare audio.

**This package stands alone.** It imports no Acervo settings, graph, database or wire vocabulary,
and `tests/unit/server/test_layering.py` enforces that. It takes a catalogue and a chain and nothing
else, which is what lets a second project use it and what keeps `acervo.models.pacing` importable in
an image that does not carry LiteLLM. `acervo.services.models` is the separate, Acervo-specific
binding layer that reads `Settings` and speaks the `llm_*` error codes.
"""

from __future__ import annotations

from acervo.models.catalogue import (
    CATALOGUE_PATH,
    Catalogue,
    Row,
    available,
    load_catalogue,
    reason,
)
from acervo.models.errors import (
    ChainExhausted,
    ProviderError,
    ProviderRefused,
    ProviderUnavailable,
    Reason,
    RETRYABLE,
    TERMINAL,
)
from acervo.models import journal
from acervo.models.results import Answer, AudioResult, ImageResult, TextResult

__all__ = [
    "Answer",
    "journal",
    "AudioResult",
    "CATALOGUE_PATH",
    "Catalogue",
    "ChainExhausted",
    "ImageResult",
    "ProviderError",
    "ProviderRefused",
    "ProviderUnavailable",
    "RETRYABLE",
    "Reason",
    "Row",
    "TERMINAL",
    "TextResult",
    "available",
    "image",
    "load_catalogue",
    "reason",
    "speech",
    "text",
]


def __getattr__(name: str):
    """`text`, `image` and `speech` arrive only when they are asked for.

    Importing them eagerly would import `call.py`, and a reader of this module would then need
    LiteLLM to exist. `scripts/ingest_vocabulary_file.py` imports `acervo.models.pacing` and the
    worker image carries no LiteLLM, so that is not a hypothetical.
    """
    if name in ("text", "image", "speech"):
        from acervo.models import call

        return getattr(call, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

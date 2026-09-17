"""Take the credentials back out of a provider's error text.

Providers routinely echo the request back in an error — the URL, the headers, sometimes the key
itself — and this repository is public. Every `detail` on every `ProviderError` goes through here at
construction, so there is no path that reaches a log or a response without it.

Lifted from `lexibeat`'s `_redact_provider_text`, with its one weakness fixed: that
version hardcoded three variable names, so a provider added later was unredacted until somebody
remembered. This one reads the names from the catalogue, which is where they are already written
down.
"""

from __future__ import annotations

import os
from typing import Callable, Iterable

LIMIT = 2000
REDACTED = "«redacted»"

# A short value is a word, not a secret. A row's `requires` holds things like a region or a
# project name as well as keys, and cutting a four-letter word out of every message that used
# it reads as a bug in Acervo rather than as discretion.
MINIMUM = 8


def redactor(names: Iterable[str]) -> Callable[[str], str]:
    """A redactor over the *current* values of `names`. Build it once, from the catalogue.

    Longest first, so a value that contains another is not left half-replaced.
    """
    secrets = sorted(
        {
            value
            for value in ((os.environ.get(name) or "").strip() for name in names)
            if len(value) >= MINIMUM
        },
        key=len,
        reverse=True,
    )

    def redact(text: str) -> str:
        cleaned = text or ""
        for secret in secrets:
            cleaned = cleaned.replace(secret, REDACTED)
        return cleaned[:LIMIT]

    return redact

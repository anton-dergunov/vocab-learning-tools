"""The three literal shapes the wire contract is built out of, and the one way to mint an id."""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

# 15 lowercase alphanumerics, minted offline by clients and stored unchanged everywhere: PocketBase,
# IndexedDB, relations and consumer manifests all carry the same string.
ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
ID_LENGTH = 15
RECORD_ID = re.compile(r"^[a-z0-9]{15}$")

# Exactly 24 characters, three fractional digits. `2026-01-01T00:00:00Z` is refused, deliberately:
# the storage columns are bounded to 24 characters and the client always writes milliseconds.
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
DEVICE_ID = re.compile(r"^[a-z0-9]{1,32}$")


def new_record_id() -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))


def is_record_id(value: str) -> bool:
    return bool(RECORD_ID.match(value))


def is_instant(value: str) -> bool:
    return bool(INSTANT.match(value))


def is_language(value: str) -> bool:
    return bool(LANGUAGE.match(value))


def instant_of(moment: "datetime") -> str:
    """A moment in the only timestamp shape the wire carries.

    Not `isoformat()`: that yields `+00:00` and six fractional digits, and `INSTANT` accepts neither.
    Anything that has a `datetime` and needs to put it on the wire comes through here.
    """
    from datetime import timezone

    utc = moment.astimezone(timezone.utc)
    return f"{utc.strftime('%Y-%m-%dT%H:%M:%S')}.{utc.microsecond // 1000:03d}Z"


def now_instant() -> str:
    """The current time in the only timestamp shape the wire carries."""
    from datetime import datetime, timezone

    return instant_of(datetime.now(timezone.utc))

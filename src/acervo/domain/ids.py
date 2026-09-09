"""The three literal shapes the wire contract is built out of, and the one way to mint an id."""

from __future__ import annotations

import re
import secrets

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


def now_instant() -> str:
    """The current time in the only timestamp shape the wire carries."""
    from datetime import datetime, timezone

    moment = datetime.now(timezone.utc)
    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{moment.microsecond // 1000:03d}Z"

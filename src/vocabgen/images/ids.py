"""Record ids, minted offline.

Acervo ids are 15 lowercase alphanumeric characters minted by the client, so the local run can mint
the `imagePrompt` ids that a later import will store unchanged — the files land under their final
names and the import is a plain write of rows that already know where they point.

Derived from the sense id rather than drawn at random, so a re-run finds the same file without
consulting an index. That is what makes the whole stage resumable by looking at the filesystem.
"""

from __future__ import annotations

import hashlib

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
ID_LENGTH = 15
_NAMESPACE = "acervo/imagePrompt/v1"


def image_prompt_id(sense_id: str) -> str:
    digest = hashlib.sha256(f"{_NAMESPACE}:{sense_id}".encode()).digest()
    value = int.from_bytes(digest, "big")
    out = []
    for _ in range(ID_LENGTH):
        value, index = divmod(value, len(ALPHABET))
        out.append(ALPHABET[index])
    return "".join(out)


def seed_for(sense_id: str, attempt: int) -> int:
    """A drawing seed that is stable for a sense and different on every retry.

    Stable so a regeneration keeps the look; different per attempt so deleting a picture you
    disliked and running again does not hand you the same picture back.
    """
    digest = hashlib.sha256(f"{_NAMESPACE}:seed:{sense_id}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 2147483647

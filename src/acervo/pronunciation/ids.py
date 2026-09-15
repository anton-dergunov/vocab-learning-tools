"""The derived id of a pronunciation.

A spoken field has at most one clip: the headword of a lexeme, the definition of a sense, the text of
an example or an attestation. So the id is a function of what is read — `(target kind, target id)` —
and recording it again, from the interface or from a sweep that does not exist yet, lands on the same
row instead of adding a second one. A removed clip is an ordinary tombstone, revived at the same id
the next time somebody presses play, which is exactly the "record it again" gesture.

The base-36 loop is written out rather than imported from `acervo.images.ids`, for the reason
`acervo.clips.ids` gives: this package may not import that one. `web/src/ids.ts` is the other half,
pinned against shared vectors from `tests/unit/pronunciation/test_ids.py` and `web/src/ids.test.ts`.
"""

from __future__ import annotations

import hashlib

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
ID_LENGTH = 15
_NAMESPACE = "acervo/pronunciation/v1"


def pronunciation_id(target_kind: str, target_id: str) -> str:
    digest = hashlib.sha256(f"{_NAMESPACE}:{target_kind}:{target_id}".encode()).digest()
    value = int.from_bytes(digest, "big")
    out = []
    for _ in range(ID_LENGTH):
        value, index = divmod(value, len(ALPHABET))
        out.append(ALPHABET[index])
    return "".join(out)

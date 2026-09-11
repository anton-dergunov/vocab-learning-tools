"""The derived id of a clip example.

There are two writers here and they do not coordinate: the interface's enrichment engine, which
searches the word you just saved, and the sweep, which walks the backlog. That is the same pair that
draws pictures, and it is why an `imagePrompt`'s id is a namespaced hash of its sense rather than
15 random characters — a client that minted a random one instead gave an imported sense two rows,
and nothing failed.

So a clip example's id is a function of the sense *and* the segment. Two writers that pick the same
segment for the same sense converge on one row, and whichever arrives second finds the work already
done or is refused as stale. A sense may still accumulate clips from different segments, which is
correct: the pair is the identity, not the sense alone.

The base-36 loop is written out rather than imported from `acervo.images.ids` on purpose — this
package may not import that one. Ten duplicated lines are cheaper than the cross-package import the
layering test forbids. `web/src/ids.ts` is the other half, and the two are pinned against shared
vectors from `tests/unit/` and `web/src/ids.test.ts`.
"""

from __future__ import annotations

import hashlib

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
ID_LENGTH = 15
_NAMESPACE = "acervo/clipExample/v1"


def clip_example_id(sense_id: str, clip_ref: str) -> str:
    digest = hashlib.sha256(f"{_NAMESPACE}:{sense_id}:{clip_ref}".encode()).digest()
    value = int.from_bytes(digest, "big")
    out = []
    for _ in range(ID_LENGTH):
        value, index = divmod(value, len(ALPHABET))
        out.append(ALPHABET[index])
    return "".join(out)

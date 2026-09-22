"""Embeddings kept beside the database, addressed by what they are embeddings *of*.

The pattern of the loop take store (`pronunciation/takes.py`): **the digest is the filename, so there
is no table and no schema.** Nothing has to be kept in step with the files, a deploy never needs a
converter for it, and because the key is the text rather than a record id it survives a rebuilt
database and a re-import, which re-mint every id. A vector is 384 floats; a vocabulary's worth is a
few megabytes, so nothing prunes it.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np


class EmbeddingCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:4] / f"{digest}.npy"

    def find(self, digest: str) -> np.ndarray | None:
        path = self._path(digest)
        if not path.is_file():
            return None
        try:
            return np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None

    def store(self, digest: str, vector: np.ndarray) -> None:
        """Atomically: two requests embedding the same text is not a conflict."""
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        np.save(buffer, np.asarray(vector, dtype=np.float32), allow_pickle=False)
        partial = path.with_name(f"{path.name}.{os.getpid()}.part")
        partial.write_bytes(buffer.getvalue())
        os.replace(partial, path)

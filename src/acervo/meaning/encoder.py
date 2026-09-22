"""The sentence encoder, pinned, and loaded only when a map is first asked for.

`models/encoder.json` names the model and the exact revision, the way `models/catalogue.json` names
providers: the server image downloads that revision once at build time, and at run time the library
is told it is offline, so a map never reaches the network. Anything with `encode(texts)` can stand in
— which is how the tests run without torch.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

PIN_PATH = Path(__file__).resolve().parents[3] / "models" / "encoder.json"


@dataclass(frozen=True)
class Pin:
    model: str
    revision: str
    prefix: str = ""


def load_pin(path: Path = PIN_PATH) -> Pin:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Pin(model=raw["model"], revision=raw["revision"], prefix=raw.get("prefix", ""))


class Encoder(Protocol):
    @property
    def model(self) -> str: ...

    def encode(self, texts: list[str]) -> np.ndarray:
        """Unit vectors, one row per text."""
        ...


class SentenceEncoder:
    """sentence-transformers on the CPU. The model is ~470 MB and half a gigabyte of memory, so it is
    loaded on the first map anyone asks for, not when the server starts."""

    def __init__(self, pin: Pin) -> None:
        self.pin = pin
        self._model = None
        self._lock = threading.Lock()

    @property
    def model(self) -> str:
        return self.pin.model

    def _loaded(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.pin.model, revision=self.pin.revision, device="cpu")
            return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vectors = self._loaded().encode([self.pin.prefix + text for text in texts], batch_size=32,
                                        normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

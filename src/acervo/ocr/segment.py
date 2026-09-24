"""Sentences in a photo's running text: Segment any Text, pinned, and loaded once.

Rules would do on clean text, and a photo's text is not clean: it carries a status bar, a URL, a
heading, show-through from the facing page and a fragment cut off by the frame, and none of those
ends in punctuation, so a rule glues each onto the sentence after it. Measured in
`experiments/photo-capture/`: rules and pySBD put the boundaries right for 69% and 74% of taps on
Vision's text, and SaT (`sat-3l-sm`) for 98%. It is also multilingual, which a rule set written for
Spanish is not.

`models/segmenter.json` names the model, its tokenizer and the exact revisions, the way
`models/encoder.json` does for the meaning map: the server image downloads them once at build time,
and at run time the hub is told it is offline, so reading a photo never reaches the network for a
model. Anything with `split(text)` can stand in — which is how the tests run without onnxruntime.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PIN_PATH = Path(__file__).resolve().parents[3] / "models" / "segmenter.json"


@dataclass(frozen=True)
class Pin:
    model: str
    revision: str
    files: tuple[str, ...]
    tokenizer: str
    tokenizer_revision: str
    tokenizer_files: tuple[str, ...]


def load_pin(path: Path = PIN_PATH) -> Pin:
    raw = json.loads(path.read_text(encoding="utf-8"))
    tokenizer = raw["tokenizer"]
    return Pin(
        model=raw["model"],
        revision=raw["revision"],
        files=tuple(raw["files"]),
        tokenizer=tokenizer["model"],
        tokenizer_revision=tokenizer["revision"],
        tokenizer_files=tuple(tokenizer["files"]),
    )


class Segmenter(Protocol):
    def split(self, text: str) -> list[tuple[int, int]]:
        """Character spans, one per sentence, in order, trimmed of surrounding space."""
        ...


class SaTSegmenter:
    """SaT on onnxruntime. About 400 MB on disk, so it is loaded once, on first use or on `warm`."""

    def __init__(self, pin: Pin) -> None:
        self.pin = pin
        self._model = None
        self._lock = threading.Lock()

    def _loaded(self):
        with self._lock:
            if self._model is None:
                from wtpsplit_lite import SaT

                model = _snapshot(self.pin.model, self.pin.revision, self.pin.files)
                tokenizer = _snapshot(
                    self.pin.tokenizer, self.pin.tokenizer_revision, self.pin.tokenizer_files
                )
                # Local directories, so the library's own hub lookups never run.
                self._model = SaT(str(model), tokenizer_name_or_path=str(tokenizer), hub_prefix=None)
            return self._model

    def warm(self) -> None:
        self._loaded()

    def split(self, text: str) -> list[tuple[int, int]]:
        if not text.strip():
            return []
        return spans_of(text, self._loaded().split(text))


def _snapshot(repository: str, revision: str, files: tuple[str, ...]) -> Path:
    """The directory holding these files at this revision, fetched only if the cache lacks them.

    File by file rather than `snapshot_download`, which lists the repository over the network even
    when every file is already cached — and the server runs with the hub switched offline.
    """
    from huggingface_hub import hf_hub_download

    paths = [Path(hf_hub_download(repository, name, revision=revision)) for name in files]
    return paths[0].parent


def spans_of(text: str, pieces: list[str]) -> list[tuple[int, int]]:
    """Where each returned piece sits in the text it came from, trimmed of surrounding space."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for piece in pieces:
        body = piece.strip()
        if not body:
            continue
        start = text.find(body, cursor)
        if start < 0:
            continue
        spans.append((start, start + len(body)))
        cursor = start + len(body)
    return spans


_shared: Segmenter | None = None
_shared_lock = threading.Lock()


def shared() -> Segmenter:
    """The process's one segmenter, built from the pin on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = SaTSegmenter(load_pin())
        return _shared


def use(segmenter: Segmenter | None) -> None:
    """Replace the process's segmenter. Tests use it; None goes back to the pinned model."""
    global _shared
    with _shared_lock:
        _shared = segmenter

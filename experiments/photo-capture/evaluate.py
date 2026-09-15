"""Scoring against the hand-written truth in the fixtures manifest.

A truth sentence is found in an engine's running text by fuzzy alignment rather than by its
segmentation, so OCR quality and sentence splitting are measured separately: the sentence CER says
how well the text was *read*, and "sentence correct" says whether the splitter handed the tap the
right *span*.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

import engines as E
import hit
import layout as L

_SPACES = re.compile(r"\s+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "«": '"', "»": '"', "‘": "'", "’": "'", "—": "–", "−": "-"})


def norm(text: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text).translate(_QUOTES)).strip()


def bare(word: str) -> str:
    """A word without surrounding punctuation or footnote digits, lowercased."""
    return re.sub(r"^[^\wáéíóúüñ]+|[^\wáéíóúüñ]+$", "", norm(word).lower())


def cer(truth: str, got: str) -> float:
    return Levenshtein.normalized_distance(norm(truth), norm(got))


def align(truth: str, text: str) -> tuple[int, int, float]:
    """Where `truth` sits in `text`: (start, end, CER of that span)."""
    if not text:
        return 0, 0, 1.0
    found = fuzz.partial_ratio_alignment(norm(truth), text, score_cutoff=0)
    start, end = found.dest_start, found.dest_end
    # partial_ratio aligns a window the length of the truth; widen or narrow by a few characters to
    # the span with the lowest distance, so a missed or extra word does not shift the whole window.
    best = (start, end, cer(truth, text[start:end]))
    for ds in range(-6, 7, 2):
        for de in range(-6, 7, 2):
            s, e = max(0, start + ds), min(len(text), end + de)
            if e > s:
                score = cer(truth, text[s:e])
                if score < best[2]:
                    best = (s, e, score)
    return best


def reading(layout: dict[str, Any]) -> dict[str, Any]:
    return L.running_text(layout)


def locate_tap(read: dict[str, Any], sentence_text: str, word: str, occurrence: int) -> dict | None:
    """The token for a truth tap inside the reference reading, found via its sentence."""
    start, end, _ = align(sentence_text, read["text"])
    matches = [t for t in read["tokens"]
               if start - 2 <= t["start"] < end + 2 and bare(t["text"]) == bare(word)]
    return matches[occurrence] if len(matches) > occurrence else None


def centroid(polygon: list[list[float]]) -> tuple[float, float]:
    return (sum(p[0] for p in polygon) / len(polygon), sum(p[1] for p in polygon) / len(polygon))


def to_variant(point: tuple[float, float], full_size: tuple[int, int], variant: E.Variant):
    """A full-frame normalised point in a variant's normalised coordinates, or None if cropped away."""
    width, height = full_size
    if variant.crop == "full":
        return point
    x0, y0, x1, y1 = E.centre_box(width, height)
    x = (point[0] * width - x0) / (x1 - x0)
    y = (point[1] * height - y0) / (y1 - y0)
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None

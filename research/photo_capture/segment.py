"""Three sentence splitters over the same running text, each returning (start, end) spans.

Printed text keeps its punctuation, which is why punctuation-driven splitters are fair arms here:
spoken-usage-retrieval's Plan 17 excluded them only because automatic captions have none.
"""

from __future__ import annotations

import re
from functools import lru_cache

ABBREVIATIONS = {
    "sr", "sra", "srta", "dr", "dra", "lic", "ing", "prof", "pp", "p", "pág", "págs", "vol", "vols",
    "núm", "n", "no", "ed", "eds", "cap", "caps", "aprox", "etc", "ej", "cf", "ca", "s", "ss", "av",
    "pres", "gral", "fig", "tel", "art", "dto", "depto", "a.c", "d.c", "ee.uu", "uu",
}
_BOUNDARY = re.compile(r"[.!?…]+[\"'”»)\]]*(?=\s+|$)")
_OPENS_SENTENCE = re.compile(r"\s+[¿¡«“\"(—–-]*[A-ZÁÉÍÓÚÜÑ0-9]")


def rules(text: str) -> list[tuple[int, int]]:
    """S0. Split after terminal punctuation when the next thing opens a sentence."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        before = text[start:match.start()].split()
        last_word = before[-1].lower().strip("(«“\"") if before else ""
        if match.group().startswith(".") and last_word.rstrip(".") in ABBREVIATIONS:
            continue
        if end < len(text) and not _OPENS_SENTENCE.match(text, end):
            continue  # "¿Por qué? dijo", or a lowercase continuation
        spans.append((start, end))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    if start < len(text) and text[start:].strip():
        spans.append((start, len(text)))
    return spans


@lru_cache(maxsize=1)
def _pysbd():
    import warnings

    warnings.filterwarnings("ignore", category=SyntaxWarning)
    import pysbd

    return pysbd.Segmenter(language="es", clean=False, char_span=True)


def pysbd_es(text: str) -> list[tuple[int, int]]:
    """S1."""
    return [(span.start, span.start + len(span.sent.rstrip())) for span in _pysbd().segment(text)]


@lru_cache(maxsize=1)
def _sat():
    from wtpsplit_lite import SaT

    return SaT("sat-3l-sm")


def sat(text: str) -> list[tuple[int, int]]:
    """S2. Segment any Text, text-only. The multilingual arm the CJK spike will need."""
    return _spans_of(text, _sat().split(text))


def _spans_of(text: str, pieces: list[str]) -> list[tuple[int, int]]:
    spans, cursor = [], 0
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


ARMS = {"S0-rules": rules, "S1-pysbd": pysbd_es, "S2-sat": sat}

#!/usr/bin/env python3
"""Step 7: does splitting on Vision's own paragraphs make rules good enough to skip SaT?

The spike's README left this untried: rules failed on OCR text (69% of boundaries right) because a
photo's text stream carries a status bar, a heading, a URL, show-through from the facing page — lines
that end in no punctuation and get glued onto the next sentence. Vision already knows those are
separate paragraphs. So: cut the text wherever Vision ended a paragraph, and split inside each piece.

From the cached readings only, so it spends no call. Those readings kept Vision's paragraph ends only
as a jump in the line counter — `engines.vision_read` adds one to it after every paragraph — which is
all this needs: a paragraph boundary is a strictly stronger cut than a block boundary, so cutting on
paragraphs covers blocks too.

    .venv/bin/python blocks.py            # prints the table the README quotes
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable

import engines as E
import score as S
import segment

Splitter = Callable[[str], list[tuple[int, int]]]
VARIANT = E.Variant("full", 2048)


def paragraph_ends(layout: dict[str, Any], read: dict[str, Any]) -> list[int]:
    """Offsets in the running text where Vision ended a paragraph."""
    words = layout["words"]
    ends = []
    for token in read["tokens"]:
        last = token["words"][-1]
        if last + 1 >= len(words):
            continue
        here, after = words[last], words[last + 1]
        jumped = after["line"] - here["line"] >= 2
        silent = after["line"] != here["line"] and here["break"] not in ("eol", "hyphen")
        if jumped or silent:
            ends.append(token["end"])
    return ends


def within(text: str, ends: list[int], split: Splitter) -> list[tuple[int, int]]:
    """`split` run inside each paragraph, never across one."""
    spans: list[tuple[int, int]] = []
    start = 0
    for end in [*ends, len(text)]:
        piece = text[start:end]
        for a, b in split(piece):
            spans.append((start + a, start + b))
        start = end
    return spans


ARMS: dict[str, Callable[[str, list[int]], list[tuple[int, int]]]] = {
    "rules": lambda text, ends: segment.rules(text),
    "sat": lambda text, ends: segment.sat(text),
    "paragraphs+rules": lambda text, ends: within(text, ends, segment.rules),
    "paragraphs+sat": lambda text, ends: within(text, ends, segment.sat),
}


def main() -> None:
    rows = S.manifest()
    taps = S.place_taps(rows)
    readings: dict[str, Any] = {}
    timings: dict[str, list[float]] = {arm: [] for arm in ARMS}
    segment.sat("warm the model")
    for row in rows:
        data, _, _ = E.prepare(S.FIXTURES / row["file"], VARIANT)
        layout = S.cached("vision", data)
        if layout is None:
            raise SystemExit(f"no cached Vision reading for {row['file']} at {VARIANT.name}")
        read = S.V.reading(S.L.rebuild_lines(layout))
        ends = paragraph_ends(layout, read)
        read["spans"] = {}
        for arm, split in ARMS.items():
            started = time.perf_counter()
            read["spans"][arm] = split(read["text"], ends)
            timings[arm].append(time.perf_counter() - started)
        read["paragraphs"] = len(ends) + 1
        readings[row["file"]] = read

    print(f"{len(taps)} taps on {len(rows)} fixtures, Vision at {VARIANT.name}\n")
    print("| Splitter | Boundary right, primary | Camera | Screenshot | Sentence right | Median time |")
    print("| --- | --- | --- | --- | --- | --- |")
    for arm in ARMS:
        results = S.score_taps(taps, {"variant": VARIANT, "readings": readings}, arm)
        primary = [r for r in results if r["class"] == "primary"]
        by = lambda kind: [r["boundaryOk"] for r in primary if r["kind"] == kind]  # noqa: E731
        print(
            f"| {arm} | {S.rate([r['boundaryOk'] for r in primary]):.0f}% "
            f"| {S.rate(by('camera')):.0f}% | {S.rate(by('screenshot')):.0f}% "
            f"| {S.rate([r['sentenceOk'] for r in primary]):.0f}% "
            f"| {1000 * statistics.median(timings[arm]):.1f} ms |"
        )
    print("\nParagraphs per page: " + ", ".join(
        f"{name.split('.')[0]} {read['paragraphs']}" for name, read in readings.items()))


if __name__ == "__main__":
    main()

"""From an engine's words to a page: tokens, lines, sentences, all in the image's own coordinates.

Pure, and deliberately so: a recorded engine answer is a test fixture, and the interface's hit test
(`web/src/photoText.ts`) is written against exactly what `page` returns.

The shape, every coordinate normalised to 0–1 from the image's top left:

    text        the page's running text; every offset below is into it
    words[]     id, text, polygons, confidence, lineId, start, end
    lines[]     id, polygon, wordIds
    sentences[] id, text, wordIds, start, end, truncatedStart, truncatedEnd

A *word* here is a token of the running text rather than an engine word: `pala-` / `bra` across a
line break is one word with two polygons, so tapping either half selects it, and a comma Vision
reports as a word of its own is a word of its own. Offsets are characters, never spaces counted as
words, so nothing in the shape assumes a script that separates words with spaces.

Reading order is the engine's. Vision returns blocks in reading order, and on every fixture the spike
photographed — a curled book page, a two-column web page — that order was right; rebuilding it would
be a second opinion with nothing to measure it against.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Sequence

from acervo.models.results import OcrWord

# What a hyphen at the end of a line can be written as. The soft hyphen is what a PDF puts there.
HYPHENS = ("-", "‐", "‑", "¬", "­")
# A sentence ends with terminal punctuation and whatever closes around it.
TERMINAL = re.compile(r"[.!?…。！？][\"'”»)\]」』]*$")
# What may open a sentence before its first letter.
OPENERS = "¿¡«“\"'(—–-「『 "

Splitter = Callable[[str], list[tuple[int, int]]]


def page(words: Sequence[OcrWord], width: int, height: int, split: Splitter) -> dict[str, Any]:
    """The whole page, ready to be tapped. `split` is the sentence splitter: text in, spans out."""
    text, tokens, lines = _running(words, width, height)
    sentences = _sentences(text, tokens, split(text))
    return {
        "text": text,
        "words": [
            {
                "id": token["id"],
                "text": token["text"],
                "polygons": token["polygons"],
                "confidence": round(token["confidence"], 3),
                "lineId": token["lineId"],
                "start": token["start"],
                "end": token["end"],
            }
            for token in tokens
        ],
        "lines": lines,
        "sentences": sentences,
    }


def _running(
    words: Sequence[OcrWord], width: int, height: int
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """The running text, its tokens, and its lines.

    A line ends where the engine says one does — a break at the end of a line, or a hyphen there —
    and wherever a paragraph ends, whether or not the engine said so.
    """
    parts: list[str] = []
    tokens: list[dict[str, Any]] = []
    # The engine words of each line, for its outline, and the tokens that touch it.
    line_pieces: list[list[OcrWord]] = [[]]
    line_tokens: list[list[str]] = [[]]
    cursor = 0
    pending: dict[str, Any] | None = None  # the first half of a hyphenated word

    for index, word in enumerate(words):
        following = words[index + 1] if index + 1 < len(words) else None
        paragraph_ends = following is None or following.paragraph != word.paragraph
        at_line_end = word.break_after in ("eol", "hyphen") or paragraph_ends
        hyphenated = (
            following is not None
            and not paragraph_ends
            and at_line_end
            and (word.break_after == "hyphen" or word.text.endswith(HYPHENS))
            # "Atelman-" / "Fourcade" is a double-barrelled name, not a broken word.
            and following.text[:1].islower()
        )
        polygon = _normalised(word.polygon, width, height)
        line = len(line_pieces) - 1
        line_pieces[line].append(word)

        if pending is not None:
            pending["text"] += word.text
            pending["polygons"].append(polygon)
            pending["confidence"] = min(pending["confidence"], word.confidence)
            parts.append(word.text)
            cursor += len(word.text)
            pending["end"] = cursor
            line_tokens[line].append(pending["id"])
            pending = None
        else:
            piece = word.text.rstrip("".join(HYPHENS)) if hyphenated else word.text
            token = {
                "id": f"w{len(tokens)}",
                "text": piece,
                "polygons": [polygon],
                "confidence": word.confidence,
                "lineId": f"l{line}",
                "start": cursor,
            }
            parts.append(piece)
            cursor += len(piece)
            token["end"] = cursor
            tokens.append(token)
            line_tokens[line].append(token["id"])
            if hyphenated:
                pending = token
                line_pieces.append([])
                line_tokens.append([])
                continue

        if following is not None and (word.break_after is not None or at_line_end):
            parts.append(" ")
            cursor += 1
        if at_line_end and following is not None:
            line_pieces.append([])
            line_tokens.append([])

    lines = [
        {"id": f"l{number}", "polygon": _line_outline(pieces, width, height), "wordIds": ids}
        for number, (pieces, ids) in enumerate(zip(line_pieces, line_tokens))
        if pieces
    ]
    return "".join(parts), tokens, lines


def _sentences(
    text: str, tokens: list[dict[str, Any]], spans: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    """Each span as a sentence of the tokens that start inside it.

    Only the page's first sentence can have lost its start to the frame and only its last can have
    lost its end: a sentence in the middle of a photo is whole by construction. The first is cut off
    when it opens in lower case, the last when it does not end with terminal punctuation.
    """
    found: list[dict[str, Any]] = []
    for start, end in spans:
        ids = [token["id"] for token in tokens if start <= token["start"] < end]
        if not ids:
            continue
        found.append({
            "id": f"s{len(found)}",
            "text": text[start:end].strip(),
            "wordIds": ids,
            "start": start,
            "end": end,
            "truncatedStart": False,
            "truncatedEnd": False,
        })
    if found:
        opening = found[0]["text"].lstrip(OPENERS)
        found[0]["truncatedStart"] = opening[:1].islower()
        found[-1]["truncatedEnd"] = TERMINAL.search(found[-1]["text"]) is None
    return found


def _normalised(
    polygon: Sequence[tuple[float, float]], width: int, height: int
) -> list[list[float]]:
    return [
        [round(min(max(x / width, 0.0), 1.0), 5), round(min(max(y / height, 0.0), 1.0), 5)]
        for x, y in polygon
    ]


def _line_outline(pieces: Sequence[OcrWord], width: int, height: int) -> list[list[float]]:
    """A line's outline: the first word's left edge and the last word's right edge.

    Vision's vertices run clockwise from the top left *of the text*, so on a tilted or rotated page
    this is still the line's own quadrilateral rather than an upright box around it. A word with any
    other number of vertices falls back to the box around every vertex of the line.
    """
    first, last = pieces[0].polygon, pieces[-1].polygon
    if len(first) == 4 and len(last) == 4:
        outline = [first[0], last[1], last[2], first[3]]
    else:
        xs = [x for piece in pieces for x, _ in piece.polygon] or [0.0]
        ys = [y for piece in pieces for _, y in piece.polygon] or [0.0]
        outline = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    return _normalised(outline, width, height)

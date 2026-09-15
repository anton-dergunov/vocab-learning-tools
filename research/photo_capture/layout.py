"""From OCR words to one running text, with a character span for every tappable token.

A token is what a tap selects. Usually it is one OCR word; a word hyphenated across a line break is
two OCR words and one token, carrying both polygons, so a tap on either half selects the whole word
and the sentence reads `transformó` rather than `trans- formó`.
"""

from __future__ import annotations

import re
from typing import Any

HYPHENS = ("-", "‐", "‑", "¬", "­")


def rebuild_lines(layout: dict[str, Any]) -> dict[str, Any]:
    """Chain detector fragments back into printed lines, following each line's own slope.

    On a curled or tilted page RapidOCR's detector breaks one printed line into several fragments and
    orders them by their top edge, so fragments of neighbouring lines interleave: measured on
    camera-07, where the characters were mostly right and the sentences unreadable. A fragment's
    successor is the nearest fragment starting just to its right at the height its right end
    reaches. Cloud Vision already returns lines in reading order and is left alone.
    """
    if layout["engine"].startswith("vision"):
        return layout
    width, height = layout["width"], layout["height"]
    groups: dict[int, list[dict[str, Any]]] = {}
    for word in layout["words"]:
        groups.setdefault(word["line"], []).append(word)

    fragments = []
    for words in groups.values():
        first, last = words[0]["polygon"], words[-1]["polygon"]
        # A word box is [top-left, top-right, bottom-right, bottom-left].
        left = ((first[0][0] + first[3][0]) / 2 * width, (first[0][1] + first[3][1]) / 2 * height)
        right = ((last[1][0] + last[2][0]) / 2 * width, (last[1][1] + last[2][1]) / 2 * height)
        tall = sum(abs(w["polygon"][3][1] - w["polygon"][0][1]) for w in words) / len(words) * height
        fragments.append({"words": words, "left": left, "right": right, "h": max(tall, 1.0)})

    successor: dict[int, int] = {}
    taken: set[int] = set()
    candidates = []
    for i, a in enumerate(fragments):
        for j, b in enumerate(fragments):
            if i == j:
                continue
            gap = b["left"][0] - a["right"][0]
            h = min(a["h"], b["h"])
            if -0.5 * h <= gap <= 4 * h and abs(b["left"][1] - a["right"][1]) <= 0.45 * h:
                candidates.append((abs(gap) + 2 * abs(b["left"][1] - a["right"][1]), i, j))
    for _, i, j in sorted(candidates):
        if i not in successor and j not in taken:
            successor[i] = j
            taken.add(j)

    chains = []
    for i in range(len(fragments)):
        if i in taken:
            continue
        chain, cursor, seen = [], i, set()
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            chain.append(fragments[cursor])
            cursor = successor.get(cursor)
        chains.append(chain)

    def start_height(chain):
        # Where the line would cross the left margin: its start height, corrected for slope so an
        # indented first line is not sorted above the line it follows.
        head = chain[0]
        tail = chain[-1]
        run = tail["right"][0] - head["left"][0]
        slope = (tail["right"][1] - head["left"][1]) / run if run > 0 else 0.0
        return head["left"][1] - slope * head["left"][0]

    words = []
    for number, chain in enumerate(sorted(chains, key=start_height)):
        for fragment_index, fragment in enumerate(chain):
            for word_index, word in enumerate(fragment["words"]):
                last = fragment_index == len(chain) - 1 and word_index == len(fragment["words"]) - 1
                words.append({**word, "line": number, "break": "eol" if last else "space"})
    return {**layout, "words": words}
LOWER_START = re.compile(r"^[a-záéíóúüñ]")


def running_text(layout: dict[str, Any]) -> dict[str, Any]:
    words = layout["words"]
    text_parts: list[str] = []
    tokens: list[dict[str, Any]] = []
    cursor = 0
    pending: dict[str, Any] | None = None  # the first half of a hyphenated word

    for index, word in enumerate(words):
        piece = word["text"]
        following = words[index + 1] if index + 1 < len(words) else None
        at_line_end = word["break"] in ("eol", "hyphen") or (
            following is not None and following["line"] != word["line"]
        )
        hyphenated = at_line_end and following is not None and (
            word["break"] == "hyphen" or piece.endswith(HYPHENS)
        ) and LOWER_START.match(following["text"]) is not None

        if pending is not None:
            # Second half: extend the token begun on the previous line.
            pending["text"] += piece
            pending["polygons"].append(word["polygon"])
            pending["confidence"] = min(pending["confidence"], word["confidence"])
            pending["words"].append(index)
            text_parts.append(piece)
            cursor += len(piece)
            pending["end"] = cursor
            token = pending
            pending = None
        else:
            token = {"start": cursor, "text": "", "polygons": [], "confidence": word["confidence"],
                     "words": []}
            if hyphenated:
                head = piece.rstrip("".join(HYPHENS))
                token.update(text=head, polygons=[word["polygon"]], words=[index])
                text_parts.append(head)
                cursor += len(head)
                token["end"] = cursor
                token["joined"] = True
                pending = token
                tokens.append(token)
                continue
            token.update(text=piece, polygons=[word["polygon"]], words=[index])
            text_parts.append(piece)
            cursor += len(piece)
            token["end"] = cursor
            tokens.append(token)

        # Vision reports punctuation as its own word with no break before it ("Baile" ","), so a
        # missing break means the next word is glued on, not spaced.
        if following is not None and (word["break"] is not None or at_line_end):
            text_parts.append(" ")
            cursor += 1
    return {"text": "".join(text_parts), "tokens": tokens}


TERMINAL = re.compile(r"[.!?…][\"'”»)\]]*$")


def flag_truncation(text: str, sentences: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """A sentence the frame cut off: the first one starting lowercase, the last one unterminated."""
    out = []
    for index, (start, end) in enumerate(sentences):
        body = text[start:end].strip()
        out.append({
            "start": start,
            "end": end,
            "text": body,
            "truncatedStart": index == 0 and bool(LOWER_START.match(body.lstrip("¿¡«“\"(—–- "))),
            "truncatedEnd": index == len(sentences) - 1 and not TERMINAL.search(body),
        })
    return out

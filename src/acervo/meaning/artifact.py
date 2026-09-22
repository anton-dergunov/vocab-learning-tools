"""One language's map, assembled — and the fingerprint that says whether it is still the map.

The artifact carries positions, regions and names, and **no vectors and no sense text**: the device
joins sense ids to its own replica, so an edited headword shows at once and a map already drawn reads
offline like everything else. The one exception is the regions' labels, which are derived text about
many senses at once and are not in the replica anywhere.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from acervo.meaning import contours, layout, regions
from acervo.meaning.text import sense_text

# Bumped whenever a parameter that changes the picture changes, so every stored map is redrawn once.
LAYOUT_VERSION = "map-1"


@dataclass(frozen=True)
class MapSense:
    sense: str
    lexeme: str
    headword: str
    pos: str
    definition: str
    glosses: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return sense_text(self.headword, self.pos, self.definition, self.glosses)


def fingerprint(model: str, pairs: Sequence[tuple[str, str]]) -> str:
    """Every sense and what it says, the encoder, and the layout's parameters. Equal fingerprints are
    the same map; anything else is drawn again."""
    body = json.dumps([LAYOUT_VERSION, model, sorted(pairs)], separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def build(senses: Sequence[MapSense], vectors: np.ndarray, *, definition_lang: str,
          previous: Mapping[str, Sequence[float]] | None = None) -> dict[str, Any]:
    """Positions, regions and their cheap labels, neighbours and contours for these senses.

    `previous` maps a sense id to where the last map put it; the new layout is fitted onto it.
    """
    ids = [s.sense for s in senses]
    init = layout.start(vectors, ids, previous) if previous and len(senses) > 3 else None
    coords = layout.layout(vectors, init)
    if previous:
        coords = layout.align(coords, ids, previous)
    cut = regions.cut(coords)
    region_of, hood_of = cut if cut is not None else (None, None)
    rank = regions.ranks(vectors, hood_of) if len(senses) else np.zeros(0)
    near = regions.neighbours(vectors, [s.lexeme for s in senses]) if len(senses) else []

    region_list: list[dict[str, Any]] = []
    if cut is not None:
        headwords = [s.headword for s in senses]
        definitions = [s.definition for s in senses]
        for level, labels, count in (("region", region_of, regions.REGIONS), ("hood", hood_of, regions.HOODS)):
            distinctive = regions.terms(definitions, labels, definition_lang)
            for index in range(count):
                members = [i for i in range(len(senses)) if labels[i] == index]
                if not members:
                    continue
                centre = coords[members].mean(axis=0)
                entry: dict[str, Any] = {
                    "id": f"{level[0]}{index}", "level": level, "index": index,
                    "x": round(float(centre[0]), 1), "y": round(float(centre[1]), 1),
                    "count": len(members),
                    "labels": {"words": regions.central_words(headwords, vectors, members),
                               "terms": distinctive.get(index, [])},
                }
                if level == "hood":
                    entry["region"] = int(region_of[members[0]])
                region_list.append(entry)

    points = [
        {
            "sense": s.sense, "lexeme": s.lexeme,
            "x": round(float(coords[i][0]), 1), "y": round(float(coords[i][1]), 1),
            "r": int(region_of[i]) if cut is not None else -1,
            "h": int(hood_of[i]) if cut is not None else -1,
            "rank": round(float(rank[i]), 3),
            "nb": near[i],
        }
        for i, s in enumerate(senses)
    ]
    return {
        "side": layout.SIDE,
        "senses": len(senses),
        "words": len({s.lexeme for s in senses}),
        "points": points,
        "regions": region_list,
        "contours": contours.contours(coords) if cut is not None else [],
    }

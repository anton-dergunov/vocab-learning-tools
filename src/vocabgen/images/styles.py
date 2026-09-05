"""The style table, and the menu a sense is offered.

The table is tracked content (`config/image-styles.yaml`). Sampling is weighted random without
replacement, seeded from the sense id, so re-running the stage offers the same menu and the whole
thing is idempotent.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

MENU_SIZE = 3


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    brief: str
    weight: float
    mono: bool


class StyleTable:
    def __init__(self, styles: Sequence[Style], digest: str) -> None:
        self.styles = tuple(styles)
        self.digest = digest
        self._by_id = {style.id: style for style in self.styles}

    def __getitem__(self, style_id: str) -> Style:
        return self._by_id[style_id]

    def __contains__(self, style_id: object) -> bool:
        return style_id in self._by_id

    def menu(self, sense_id: str, weights: Mapping[str, float] | None = None) -> tuple[Style, ...]:
        """Three styles for one sense, best first, deterministic in the sense id.

        Weighted sampling without replacement. A weight of zero switches a style off entirely; the
        settings screen will drive these, and until it exists every style is equally likely.
        """
        pool = [
            (style, float((weights or {}).get(style.id, style.weight)))
            for style in self.styles
        ]
        pool = [(style, weight) for style, weight in pool if weight > 0]
        if not pool:
            raise ValueError("Every style is switched off, so no menu can be offered.")

        rng = random.Random(int.from_bytes(hashlib.sha256(sense_id.encode()).digest()[:8], "big"))
        chosen: list[Style] = []
        while pool and len(chosen) < MENU_SIZE:
            total = sum(weight for _, weight in pool)
            target = rng.random() * total
            for index, (style, weight) in enumerate(pool):
                target -= weight
                if target <= 0:
                    chosen.append(style)
                    pool.pop(index)
                    break
            else:
                chosen.append(pool.pop()[0])
        return tuple(chosen)


def load_styles(path: str | Path) -> StyleTable:
    source = Path(path)
    raw = source.read_bytes()
    data = yaml.safe_load(raw) or {}
    entries = data.get("styles") or {}
    if not isinstance(entries, dict) or not entries:
        raise ValueError(f"{source} defines no styles.")

    styles = []
    for style_id, fields in entries.items():
        if not isinstance(fields, dict):
            raise ValueError(f"Style {style_id!r} must be a mapping.")
        brief = str(fields.get("brief", "")).strip()
        if not brief:
            raise ValueError(f"Style {style_id!r} has no brief.")
        styles.append(
            Style(
                id=str(style_id),
                label=str(fields.get("label", style_id)),
                brief=brief,
                weight=float(fields.get("weight", 1)),
                mono=bool(fields.get("mono", False)),
            )
        )
    return StyleTable(styles, hashlib.sha256(raw).hexdigest()[:12])

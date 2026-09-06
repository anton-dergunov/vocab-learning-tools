"""The style table.

Tracked content (`config/image-styles.yaml`). Every enabled style is offered to the brief writer,
which picks the one that suits the meaning.

Round 1 of `experiments/sense-images` offered three sampled by weight instead, and the scene ended
up being written to fit a style that had arrived at random: a period style dragged the setting into
its period, an architectural style dragged it into its architecture, and five of seven rejections
traced back to that. Variety is still wanted — it is what keeps a deck of hundreds distinctive — but
buying it by dice roll costs the one thing the picture is for. The writer is asked for variety
directly instead, and whether that is enough is the open question round 2 measures.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    brief: str
    when: str
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

    def offer(self, weights: Mapping[str, float] | None = None,
              rotate: str | None = None) -> tuple[Style, ...]:
        """Every style the owner has left switched on.

        A weight of zero switches one off. The settings screen will drive these; until it exists
        every style is on, which is what the reviewer asked for.

        `rotate` turns the list by a stable amount derived from that key, normally the lexeme id.
        Round 2 offered the list in table order and the writer picked the first row,
        `cinematic-photoreal`, seven times in seventeen — position was doing work that fitness was
        supposed to do. Rotating costs nothing and removes the anchor without taking the choice
        away.
        """
        offered = [
            style for style in self.styles
            if float((weights or {}).get(style.id, style.weight)) > 0
        ]
        if not offered:
            raise ValueError("Every style is switched off, so none can be offered.")
        if rotate:
            turn = int.from_bytes(hashlib.sha256(rotate.encode()).digest()[:4], "big") % len(offered)
            offered = offered[turn:] + offered[:turn]
        return tuple(offered)


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
                when=str(fields.get("when", "")).strip(),
                weight=float(fields.get("weight", 1)),
                mono=bool(fields.get("mono", False)),
            )
        )
    return StyleTable(styles, hashlib.sha256(raw).hexdigest()[:12])

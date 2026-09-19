"""The story-type table.

Tracked content (`config/story-types.yaml`), read the way `images/styles.py` reads its own: a
dataclass per row, a digest of the file so a prompt version moves when the wording does, and no
opinion in the code about which types exist.

The one piece of judgement here is `style_for`. A story's pictures must all be in **one** style —
that is what makes four images look like four parts of one thing rather than four unrelated
drawings — so the style is chosen once, per story, and every part is drawn in it. Which is the
opposite of a sense image, where variety across a word's senses is the entire point.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import yaml

TYPES_PATH = Path(__file__).resolve().parents[3] / "config" / "story-types.yaml"


@dataclass(frozen=True)
class StoryType:
    id: str
    label: str
    emoji: str
    brief: str
    styles: tuple[str, ...]


class StoryTypes:
    def __init__(self, types: Sequence[StoryType], digest: str) -> None:
        self.types = tuple(types)
        self.digest = digest
        self._by_id = {one.id: one for one in self.types}

    def __getitem__(self, type_id: str) -> StoryType:
        return self._by_id[type_id]

    def __contains__(self, type_id: object) -> bool:
        return type_id in self._by_id

    def get(self, type_id: str) -> StoryType | None:
        return self._by_id.get(type_id)

    def surprise(self, key: str) -> StoryType:
        """A type, chosen by something stable rather than by the clock.

        Keyed on the story's own id, so Try again on a story that was never written reaches for the
        same kind of story rather than quietly becoming a different one.
        """
        return self.types[_seed(key) % len(self.types)]

    def style_for(self, story_type: StoryType, key: str, allowed: Sequence[str] | None = None) -> str:
        """One style for the whole story, rotated per story so a deck of them is not all one look.

        `allowed` is the owner's switched-on styles. A type whose every suggestion has been switched
        off falls back to the full allowed list rather than to nothing: the owner turned those
        styles off, not this kind of story.
        """
        offered = [one for one in story_type.styles if allowed is None or one in allowed]
        if not offered:
            offered = sorted(allowed or ())
        if not offered:
            return ""
        return offered[_seed(f"{key}:{story_type.id}") % len(offered)]


def _seed(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def load_types(path: Path | None = None) -> StoryTypes:
    source = path or TYPES_PATH
    raw = source.read_bytes()
    document = yaml.safe_load(raw.decode()) or {}
    entries = document.get("types") or {}
    types = [
        StoryType(
            id=str(type_id),
            label=str(entry.get("label") or type_id),
            emoji=str(entry.get("emoji") or ""),
            brief=" ".join(str(entry.get("brief") or "").split()),
            styles=tuple(str(one) for one in (entry.get("styles") or [])),
        )
        for type_id, entry in entries.items()
    ]
    if not types:
        raise ValueError(f"{source} declares no story types.")
    return StoryTypes(types, hashlib.sha256(raw).hexdigest()[:12])


# A module-level cache, because the file is read on every request that offers the dialog and it
# never changes while the process runs. `images/styles.py` reloads instead; that one is read once a
# job, this one once a keystroke-ish, and neither pattern is worth making uniform.
#
# Named `story_types` rather than `types` so it cannot shadow this module where both are imported,
# which it did on the first call site that tried.
_TABLE: StoryTypes | None = None


def story_types() -> StoryTypes:
    global _TABLE
    if _TABLE is None:
        _TABLE = load_types()
    return _TABLE

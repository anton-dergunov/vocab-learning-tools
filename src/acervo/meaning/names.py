"""A model names the regions: the request, and a reply read with suspicion.

The cheap names — the words nearest a region's centre — read as lists; a model's read as places.
One call names every region and neighbourhood of a layout at once, so sibling names can be kept
distinct. The prompt itself is content, in `prompts/acervo_map_names.md`; this module lays out the
groups and reads the answer, and knows nothing of who asked.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MAX_LENGTH = 40


def groups(regions: Iterable[Mapping[str, Any]], members: Mapping[str, Sequence[str]]) -> str:
    """Each group's id, level and parent, then its members most central first."""
    lines = []
    for region in regions:
        parent = f" (inside r{region['region']})" if region.get("level") == "hood" else ""
        lines.append(f"## {region['id']} — {region['level']}{parent}")
        lines.extend(f"- {member}" for member in members.get(region["id"], ()))
        lines.append("")
    return "\n".join(lines)


def parse_reply(reply: Any, known: Iterable[str]) -> dict[str, str]:
    """Only ids that were asked about, only non-empty strings, trimmed and bounded. A name the model
    invented for a region that does not exist is dropped, not trusted."""
    if not isinstance(reply, Mapping):
        return {}
    wanted = set(known)
    out: dict[str, str] = {}
    for key, value in reply.items():
        if key not in wanted or not isinstance(value, str):
            continue
        name = " ".join(value.split()).strip(" .·")
        if name:
            out[key] = name[:MAX_LENGTH].rstrip()
    return out

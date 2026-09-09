"""What compiled dictionaries this server holds."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("acervo.dictionaries")


def installed(directory: Path) -> list[dict[str, Any]]:
    """The metadata sidecar of every artifact on disk. A dictionary with no `.json` is a failed build."""
    try:
        names = sorted(Path(directory).iterdir())
    except OSError:
        return []
    found: list[dict[str, Any]] = []
    for path in names:
        if path.is_dir() or path.suffix != ".json":
            continue
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A half-written artifact must not take the whole list down with it.
            logger.info("Acervo: ignoring unreadable dictionary metadata %s", path.name)
            continue
        if isinstance(metadata, dict) and metadata.get("id"):
            found.append(metadata)
    found.sort(key=lambda entry: str(entry["id"]))
    return found

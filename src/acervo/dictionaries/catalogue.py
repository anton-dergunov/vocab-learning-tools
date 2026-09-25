"""The tracked list of dictionaries Acervo knows about.

`docs/external-dictionaries.md` §9: Acervo ships the *catalogue*, never the data. This file
is a set of facts and URLs; the download happens between the owner and the source, and the compiled
artifact never enters the repository.

The same JSON is read by two very different things — this module, and the web build, which imports
it to render the Dictionaries pane without fetching anything. Keep it declarative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOGUE_PATH = Path(__file__).resolve().parents[3] / "dictionaries" / "catalogue.json"

OFFLINE_FORMATS = {"wiktextract", "cc-cedict", "jmdict", "freedict-tei", "moedict", "pyglossary"}


@dataclass(frozen=True)
class CatalogueEntry:
    id: str
    name: str
    kind: str                       # offline | online | link
    sourceLang: str
    targetLang: str
    licence: str
    attribution: str
    url: str
    tier: str = "fields"
    format: str | None = None
    note: str | None = None
    approxDownloadBytes: int | None = None
    approxInstalledBytes: int | None = None
    options: dict[str, Any] | None = None

    @property
    def option_map(self) -> dict[str, Any]:
        return self.options or {}

    def option(self, name: str, default: Any = None) -> Any:
        return self.option_map.get(name, default)


def load_catalogue(path: Path | None = None) -> list[CatalogueEntry]:
    document = json.loads((path or CATALOGUE_PATH).read_text(encoding="utf-8"))
    return [CatalogueEntry(**row) for row in document["dictionaries"]]


def find(identifier: str, path: Path | None = None) -> CatalogueEntry:
    for entry in load_catalogue(path):
        if entry.id == identifier:
            return entry
    raise KeyError(f"no dictionary {identifier!r} in the catalogue")


def buildable(path: Path | None = None) -> list[CatalogueEntry]:
    """Rows the compiler can actually produce an artifact for.

    Online sources are answered by a server route and link-outs are a URL and nothing else, so
    neither has anything to compile.
    """
    return [entry for entry in load_catalogue(path) if entry.kind == "offline"]

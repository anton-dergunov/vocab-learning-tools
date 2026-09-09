"""The tracked list of providers Acervo knows about.

`models/catalogue.json` ships the *list* and never a credential: `keyEnv` and `requires` name
environment variables, and a value never appears in the file. It is the only place a provider's
model id, endpoint and capabilities are written down, and — unlike the dictionary artifact, which is
described twice because one reader runs in a browser — it is described once, here, because the only
reader is Python.

Row order is the default preference order. With no chain configured, every row this deployment is
credentialed for serves the kind, in file order.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOGUE_PATH = Path(__file__).resolve().parents[3] / "models" / "catalogue.json"

KINDS = ("text", "image", "audio")
SCHEMA_MODES = ("native", "prompt", "unsupported")

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ADC_FILE = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


class CatalogueError(Exception):
    """The catalogue itself is wrong. A mistake to fix in the file, never at runtime."""


@dataclass(frozen=True)
class Row:
    id: str
    label: str
    kinds: tuple[str, ...]
    litellm: dict[str, str] = field(default_factory=dict)
    adapter: dict[str, str] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    keyEnv: str | None = None
    requires: tuple[str, ...] = ()
    auth: str | None = None
    baseUrl: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Call arguments whose values live in the environment: {argument: VARIABLE}. Vertex needs
    # its project passed explicitly rather than read from ADC, and saying so as data keeps the
    # call path free of a per-provider branch.
    passes: dict[str, str] = field(default_factory=dict)
    notes: str | None = None

    def serves(self, kind: str) -> bool:
        return kind in self.kinds

    def model_for(self, kind: str) -> str:
        """The model id for this kind — LiteLLM's `provider/model` form, or the adapter's own."""
        if kind in self.litellm:
            return self.litellm[kind]
        if kind in self.models:
            return self.models[kind]
        raise CatalogueError(f"{self.id} declares {kind} but names no model for it")

    def params_for(self, kind: str) -> dict[str, Any]:
        return dict(self.params.get(kind) or {})

    @property
    def schema_mode(self) -> str:
        return str(self.capabilities.get("jsonSchema") or "prompt")

    @property
    def secret_names(self) -> tuple[str, ...]:
        """Every environment variable this row reads. What `redact.py` snapshots."""
        return tuple(dict.fromkeys(
            name for name in (self.keyEnv, *self.requires, *self.passes.values()) if name
        ))


@dataclass(frozen=True)
class Catalogue:
    version: int
    note: str
    rows: tuple[Row, ...]

    def __iter__(self):
        return iter(self.rows)

    def find(self, identifier: str) -> Row:
        for row in self.rows:
            if row.id == identifier:
                return row
        raise KeyError(identifier)

    def serving(self, kind: str) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if row.serves(kind))


def _validate(row: Row) -> None:
    if not row.kinds:
        raise CatalogueError(f"{row.id} declares no kinds")
    for kind in row.kinds:
        if kind not in KINDS:
            raise CatalogueError(f"{row.id} declares an unknown kind {kind!r}")
        # The checkable form of "add a `litellm` field to the row rather than deriving it":
        # exactly one of the two ways to reach a provider, for every kind the row claims.
        by_library = kind in row.litellm
        by_adapter = kind in row.adapter
        if by_library and by_adapter:
            raise CatalogueError(f"{row.id} routes {kind} through both LiteLLM and an adapter")
        if not by_library and not by_adapter:
            raise CatalogueError(f"{row.id} declares {kind} but names neither a model nor an adapter")
        if by_adapter and kind not in row.models:
            raise CatalogueError(f"{row.id} routes {kind} through an adapter but names no model")
    if row.schema_mode not in SCHEMA_MODES:
        raise CatalogueError(f"{row.id} declares an unknown jsonSchema mode {row.schema_mode!r}")
    if row.keyEnv and row.keyEnv in row.passes.values():
        raise CatalogueError(f"{row.id} passes its key as an ordinary call argument")
    for name in _PLACEHOLDER.findall(row.baseUrl or ""):
        # A key does not belong in a URL. This is the locked contract as an assertion rather than
        # as a comment, because a base URL is the one field that travels into logs and error text.
        if name == row.keyEnv:
            raise CatalogueError(f"{row.id} interpolates its key into baseUrl")
        if name not in row.requires:
            raise CatalogueError(f"{row.id} interpolates {name}, which it does not require")


def load_catalogue(path: Path | None = None) -> Catalogue:
    document = json.loads((path or CATALOGUE_PATH).read_text(encoding="utf-8"))
    rows: list[Row] = []
    seen: set[str] = set()
    for entry in document["providers"]:
        row = Row(
            **{
                **entry,
                "kinds": tuple(entry["kinds"]),
                "requires": tuple(entry.get("requires") or ()),
            }
        )
        if row.id in seen:
            raise CatalogueError(f"two rows share the id {row.id!r}")
        seen.add(row.id)
        _validate(row)
        rows.append(row)
    return Catalogue(version=document["version"], note=document["note"], rows=tuple(rows))


def reason(row: Row) -> str | None:
    """The first unmet requirement, or None when this row can be called.

    It names an environment variable and never carries a value: `GET /health` serves this
    unauthenticated, and a reason that quoted what it found would be a credential on the wire.
    """
    if row.keyEnv and not (os.environ.get(row.keyEnv) or "").strip():
        return f"{row.keyEnv} is not set"
    for name in row.requires:
        if not (os.environ.get(name) or "").strip():
            return f"{name} is not set"
    if row.auth == "adc" and not _adc_present():
        return "Google application default credentials are not configured"
    return None


def available(row: Row) -> bool:
    return reason(row) is None


def _adc_present() -> bool:
    """Vertex authenticates by ADC, so 'is it configured' is a file question, not a variable one.

    This is what makes the row present on a workstation that has run `gcloud auth
    application-default login` and absent on a server that has not, with nothing to configure
    either way.
    """
    if (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip():
        return True
    try:
        return _ADC_FILE.is_file()
    except OSError:
        return False


def base_url(row: Row) -> str | None:
    """This row's base URL with its `requires` variables filled in, or None when it has none."""
    if not row.baseUrl:
        return None
    return _PLACEHOLDER.sub(lambda match: os.environ.get(match.group(1), ""), row.baseUrl)


def key(row: Row) -> str | None:
    return (os.environ.get(row.keyEnv) or "").strip() or None if row.keyEnv else None


def passed(row: Row) -> dict[str, str]:
    """The row's environment-sourced call arguments, skipping any that are unset."""
    found = {}
    for argument, name in row.passes.items():
        value = (os.environ.get(name) or "").strip()
        if value:
            found[argument] = value
    return found

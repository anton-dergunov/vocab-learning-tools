"""The tracked list of providers Acervo knows about.

`models/catalogue.json` ships the *list* and never a credential: `keyEnv` and `requires` name
environment variables, and a value never appears in the file. It is the only place a provider's
model id, endpoint and capabilities are written down, and — unlike the dictionary artifact, which is
described twice because one reader runs in a browser — it is described once, here, because the only
reader is Python.

Row order is the default preference order, and within a row so is model order. With no chain
configured the walk is provider by provider and, inside each, model by model: every credentialed row
that serves the kind, each of its models for that kind in turn. A row names *several* models per kind
because a free tier is metered per model — two models with 500 requests a day each are a thousand
requests a day, and the second is reached by the first one's 429.

The unit of choice is therefore a (provider, model) pair, not a provider. Settings ▸ Providers
enables, disables and reorders those pairs; this file is the list they are chosen from and the order
they fall back in when nobody has chosen.
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
    # {kind: [model, ...]}, in the order they are tried. Always a list, even of one: a free tier
    # is metered per model, so "which model" is as much a choice as "which provider".
    litellm: dict[str, list[str]] = field(default_factory=dict)
    adapter: dict[str, str] = field(default_factory=dict)
    models: dict[str, list[str]] = field(default_factory=dict)
    keyEnv: str | None = None
    requires: tuple[str, ...] = ()
    auth: str | None = None
    # The variable that points at this row's credentials *file*, for a provider that will not
    # authenticate from a value. Not in `requires`: on a workstation the credentials are found
    # without it, so demanding it would make an available row look unavailable.
    authEnv: str | None = None
    # An optional guard: the variable naming which account this row is *allowed* to spend. Set it
    # and the row will not be used unless its credentials prove they belong to that account.
    accountEnv: str | None = None
    baseUrl: str | None = None
    # Where the owner reads their own usage and spend. Interpolated like `baseUrl` and under the
    # same rule — a `requires` name, never a key. Settings ▸ Providers is what renders it; there
    # is no way to ask a provider for a usage figure over its API, so a link is the honest answer.
    usageUrl: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Call arguments whose values live in the environment: {argument: VARIABLE}. Vertex needs
    # its project passed explicitly rather than read from ADC, and saying so as data keeps the
    # call path free of a per-provider branch.
    passes: dict[str, str] = field(default_factory=dict)
    notes: str | None = None

    def serves(self, kind: str) -> bool:
        return kind in self.kinds

    def models_for(self, kind: str) -> tuple[str, ...]:
        """Every model this row offers for a kind, in the order they are tried.

        LiteLLM's `provider/model` form, or the adapter's own ids where the row routes that kind
        through an adapter.
        """
        found = self.litellm.get(kind) or self.models.get(kind)
        if not found:
            raise CatalogueError(f"{self.id} declares {kind} but names no model for it")
        return tuple(found)

    def params_for(self, kind: str) -> dict[str, Any]:
        return dict(self.params.get(kind) or {})

    @property
    def schema_mode(self) -> str:
        return str(self.capabilities.get("jsonSchema") or "prompt")

    @property
    def secret_names(self) -> tuple[str, ...]:
        """Every environment variable this row reads. What `redact.py` snapshots."""
        return tuple(dict.fromkeys(
            name
            for name in (self.keyEnv, self.authEnv, *self.requires, *self.passes.values())
            if name
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
        named = row.litellm.get(kind) if by_library else row.models.get(kind)
        if not isinstance(named, list) or not named or not all(isinstance(m, str) and m for m in named):
            raise CatalogueError(
                f"{row.id} must name {kind} models as a non-empty list, even for a single model"
            )
        if len(set(named)) != len(named):
            raise CatalogueError(f"{row.id} names the same {kind} model twice")
    if row.schema_mode not in SCHEMA_MODES:
        raise CatalogueError(f"{row.id} declares an unknown jsonSchema mode {row.schema_mode!r}")
    if row.keyEnv and row.keyEnv in row.passes.values():
        raise CatalogueError(f"{row.id} passes its key as an ordinary call argument")
    # `requires` names are the row's non-secret deployment facts — a project, an account id, a
    # local URL — and they are shown to the owner in full, both interpolated into `usageUrl` and
    # listed in Settings ▸ Providers. A key among them would be published by either route.
    if row.keyEnv and row.keyEnv in row.requires:
        raise CatalogueError(f"{row.id} lists its key among the settings it shows the owner")
    for field_name, template in (("baseUrl", row.baseUrl), ("usageUrl", row.usageUrl)):
        for name in _PLACEHOLDER.findall(template or ""):
            # A key does not belong in a URL. This is the locked contract as an assertion rather
            # than as a comment: a base URL travels into logs and error text, and a usage link is
            # rendered in the interface and clicked into a browser's history.
            if name == row.keyEnv:
                raise CatalogueError(f"{row.id} interpolates its key into {field_name}")
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
    if row.auth == "adc" and not _adc_present(row.authEnv):
        return "Google application default credentials are not configured"
    return _wrong_account(row)


def _wrong_account(row: Row) -> str | None:
    """Refuse a row whose credentials are not the account it was told to use.

    A machine can hold a work Google login and a personal one, and application default credentials
    are simply whichever was signed in last — so "which account is this spending?" can change under
    a project without anything in Acervo changing. Naming the expected account turns that from a
    thing to notice afterwards into a thing that cannot happen.

    Deliberately strict: an account that cannot be *proved* is refused, not assumed. A plain
    `gcloud auth application-default login` file does not record which account wrote it, so setting
    this guard is also a decision to use a service-account key, which does. Half a guard that passes
    when it cannot check is not a guard.
    """
    if not row.accountEnv:
        return None
    expected = (os.environ.get(row.accountEnv) or "").strip()
    if not expected:
        return None
    found = identity(row)
    if found is None:
        return (
            f"{row.accountEnv} names the account these credentials must belong to, and they do not "
            "say which account they are. A service-account key does."
        )
    if found != expected:
        return f"these credentials belong to {found}, and {row.accountEnv} names another account"
    return None


def available(row: Row) -> bool:
    return reason(row) is None


def _adc_present(named: str | None) -> bool:
    """Vertex authenticates by ADC, so 'is it configured' is a file question, not a variable one.

    This is what makes the row present on a workstation that has run `gcloud auth
    application-default login` and absent on a server that has not, with nothing to configure
    either way. A server says so with the row's `authEnv`, pointing at a mounted service-account
    key — Google will not take a key as a value, which is why this is the one credential that
    travels as a file.
    """
    if named and (os.environ.get(named) or "").strip():
        return True
    try:
        return _ADC_FILE.is_file()
    except OSError:
        return False


def identity(row: Row) -> str | None:
    """Whose credentials this row would use, for a row that authenticates by a file.

    A service-account key names its own identity in `client_email`, and that is the answer. The file
    `gcloud auth application-default login` writes usually does not — measured: it carries an
    `account` field and leaves it empty — so a plain user login returns None here and the interface
    says only that ADC is in use. That difference is a real argument for a key on a machine that
    holds more than one Google login: "which account is Acervo spending?" becomes answerable without
    running `gcloud`.

    Only the naming fields are read — never the private key, never the refresh token.
    """
    if row.auth != "adc":
        return None
    path = (os.environ.get(row.authEnv) or "").strip() if row.authEnv else ""
    try:
        document = json.loads(Path(path or _ADC_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    named = document.get("client_email") or document.get("account")
    return str(named) if isinstance(named, str) and named else None


def base_url(row: Row) -> str | None:
    """This row's base URL with its `requires` variables filled in, or None when it has none."""
    return _filled(row.baseUrl)


def usage_url(row: Row) -> str | None:
    """Where the owner reads their own usage for this provider, or None when the row names nowhere.

    No provider Acervo speaks to serves a usage figure over its API, so this is a link rather than a
    number. It is filled in from the environment for the same reason `baseUrl` is: a console URL
    wants the account or project, and that is a deployment fact rather than a tracked one.
    """
    return _filled(row.usageUrl)


def _filled(template: str | None) -> str | None:
    if not template:
        return None
    return _PLACEHOLDER.sub(lambda match: os.environ.get(match.group(1), ""), template)


def key(row: Row) -> str | None:
    return (os.environ.get(row.keyEnv) or "").strip() or None if row.keyEnv else None


# Enough of a key to tell two of them apart, and never enough to use. Four at each end of a
# thirty-nine character token leaves thirty-one unknown, which is not a credential by any measure —
# and it is the difference between "a key is set" and "*that* key is set", which is the question
# asked when a rotation half-happened or two accounts are in play.
HINT_EDGE = 4
# Below this a quarter of the value would be showing. Nothing Acervo talks to issues a key that
# short, so this is a guard against a future row rather than a case that exists.
HINT_MINIMUM = 16


def key_hint(row: Row) -> str | None:
    """This row's key as its first and last four characters, or None when it has none set.

    A key that is set but too short to abbreviate safely comes back as a bare ellipsis: the caller
    still learns that a value is present, which is the part that matters, without the value.
    """
    value = key(row)
    if value is None:
        return None
    if len(value) < HINT_MINIMUM:
        return "…"
    return f"{value[:HINT_EDGE]}…{value[-HINT_EDGE:]}"


def row_settings(row: Row) -> tuple[tuple[str, str], ...]:
    """This row's `requires` variables and their values, in the order the row lists them.

    Safe to show in full, and structurally so: `_validate` refuses a row whose `keyEnv` appears
    here. These are the facts that distinguish one deployment from another — which Google project,
    which Cloudflare account — and `usageUrl` already interpolates exactly these values into the
    same response.
    """
    return tuple((name, (os.environ.get(name) or "").strip()) for name in row.requires)


def passed(row: Row) -> dict[str, str]:
    """The row's environment-sourced call arguments, skipping any that are unset."""
    found = {}
    for argument, name in row.passes.items():
        value = (os.environ.get(name) or "").strip()
        if value:
            found[argument] = value
    return found

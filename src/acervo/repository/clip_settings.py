"""How this owner wants the spoken-usage corpus consulted. One row per owner, or none.

The same three-state doctrine as `image_settings` and `model_selection`, and for the same reason:
**no record means "use the deployment default"**. Nothing creates a row eagerly and there is no
`ensure_` function, so every read is a pure read with nothing to write when it is missing. Eager
creation would have to invent a value, and snapshotting today's default would freeze it at the
instant the account was made.

One field, honestly. Which channels the corpus harvests is the retrieval service's own catalogue
(`docs/plans/spoken-clips.md` §2.10) and Acervo ships no copy of it; how many candidates a call sees
is a research knob that belongs in `docs/plans/clip-selection-experiment.md`, not in a settings
screen. A table with one column is the right size for one decision.

This module stores what it is given, exactly as `image_settings` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction


class ClipSettings(Mapping):
    """The owner's answer, or the deployment default when they have not given one.

    A `Mapping` so a route can return it as a document without a second shape to keep in step, and
    `chosen` is what says whether a row exists — which the settings screen needs in order to show
    "following the default" rather than showing the default as though it had been picked.
    """

    __slots__ = ("search_enabled", "chosen")

    def __init__(self, *, search_enabled: bool = True, chosen: bool = False) -> None:
        self.search_enabled = bool(search_enabled)
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {"searchEnabled": self.search_enabled, "chosen": self.chosen}[key]

    def __iter__(self):
        return iter(("searchEnabled", "chosen"))

    def __len__(self) -> int:
        return 2


def _read(row: Any) -> ClipSettings:
    if row is None:
        return ClipSettings()
    return ClipSettings(search_enabled=row["search_enabled"], chosen=True)


def settings(owner: str) -> ClipSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.clip_settings).where(tables.clip_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(owner: str, *, search_enabled: bool | None = None) -> ClipSettings:
    """Change only what is named. Returns the whole stored document, so a caller echoes disk.

    Read-modify-write inside one `transaction()`, which is `BEGIN IMMEDIATE`, so check-then-insert
    cannot interleave with a second save and the unique index is never reached in anger.

    There is deliberately no way to *forget* a row, as in `image_settings`: the one field has a
    value that is meaningful on its own, so following the deployment default is a state you have
    simply not left rather than one you can be trapped outside of.
    """
    with transaction() as connection:
        row = connection.execute(
            select(tables.clip_settings).where(tables.clip_settings.c.owner == owner)
        ).mappings().first()
        current = _read(row)

        wanted = ClipSettings(
            search_enabled=current.search_enabled if search_enabled is None else search_enabled,
            chosen=True,
        )
        values = {"search_enabled": wanted.search_enabled, "edited_at": now_instant()}

        if row is None:
            connection.execute(
                tables.clip_settings.insert().values(id=new_record_id(), owner=owner, **values)
            )
        else:
            connection.execute(
                tables.clip_settings.update()
                .where(tables.clip_settings.c.id == row["id"])
                .values(**values)
            )
        return wanted

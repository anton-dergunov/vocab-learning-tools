"""The owner's standing rules for generated text. One row per owner, or none.

The same doctrine as `clip_settings`: **no record means no rules**, nothing creates a row eagerly,
and every read is a pure read. Unlike the other settings there is no deployment default to follow —
empty is the default, and a row holding an empty string says the same thing as no row at all.

This module stores what it is given; the service validates it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction


class PromptRules(Mapping):
    """The owner's rules, as the route returns them."""

    __slots__ = ("rules", "chosen")

    def __init__(self, *, rules: str = "", chosen: bool = False) -> None:
        self.rules = rules
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {"rules": self.rules, "chosen": self.chosen}[key]

    def __iter__(self):
        return iter(("rules", "chosen"))

    def __len__(self) -> int:
        return 2


def settings(owner: str) -> PromptRules:
    with reading() as connection:
        row = connection.execute(
            select(tables.prompt_rules).where(tables.prompt_rules.c.owner == owner)
        ).mappings().first()
    return PromptRules() if row is None else PromptRules(rules=row["rules"], chosen=True)


def save(owner: str, *, rules: str) -> PromptRules:
    """Replace the rules. Read-modify-write inside one `BEGIN IMMEDIATE`, as `clip_settings` does."""
    with transaction() as connection:
        row = connection.execute(
            select(tables.prompt_rules).where(tables.prompt_rules.c.owner == owner)
        ).mappings().first()
        values = {"rules": rules, "edited_at": now_instant()}
        if row is None:
            connection.execute(
                tables.prompt_rules.insert().values(id=new_record_id(), owner=owner, **values)
            )
        else:
            connection.execute(
                tables.prompt_rules.update()
                .where(tables.prompt_rules.c.id == row["id"])
                .values(**values)
            )
    return PromptRules(rules=rules, chosen=True)

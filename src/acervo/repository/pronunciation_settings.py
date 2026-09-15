"""How this owner wants words pronounced. One row per owner, or none — and none is a real answer.

The `image_settings` doctrine: **no record means "use the deployment default"**, nothing creates a
row eagerly, and every read is a pure read. Server state rather than a device preference, because the
recording happens on the server — a phone that has never opened Settings still gets the voices the
owner chose. Whether a clip is *kept on a device* is the opposite case and lives on the device.

This module stores what it is given. Which voices exist is the catalogue's question, and
`acervo.services.pronunciations` is where a document is held to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

PREGENERATED = ("headword", "definitions", "examples")


class PronunciationSettings(Mapping):
    """The owner's answer, or the default when they have not given one. A `Mapping`, like `ImageSettings`."""

    __slots__ = ("pregenerate", "expressive", "voices", "chosen")

    def __init__(
        self,
        *,
        pregenerate: Mapping[str, Any] | None = None,
        expressive: bool = True,
        voices: Mapping[str, Any] | None = None,
        chosen: bool = False,
    ) -> None:
        given = pregenerate if isinstance(pregenerate, Mapping) else {}
        # Every key present and boolean, so a hand-edited row with a stray key or a string cannot
        # switch recording on by accident.
        self.pregenerate = {name: given.get(name) is True for name in PREGENERATED}
        self.expressive = bool(expressive)
        self.voices = _voices(voices)
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {
            "pregenerate": dict(self.pregenerate),
            "expressive": self.expressive,
            "voices": self.voices,
            "chosen": self.chosen,
        }[key]

    def __iter__(self):
        return iter(("pregenerate", "expressive", "voices", "chosen"))

    def __len__(self) -> int:
        return 4

    def voice(self, provider: str, model: str, language: str) -> str | None:
        """The voice chosen for this pair in this language, widening `es-MX` to `es`, or None."""
        chosen = self.voices.get(provider, {}).get(model, {})
        parts = language.split("-")
        for count in range(len(parts), 0, -1):
            if found := chosen.get("-".join(parts[:count])):
                return found
        return None


def _voices(value: Any) -> dict[str, dict[str, dict[str, str]]]:
    """Only the well-formed part of a stored voice document; anything else is dropped, not raised."""
    found: dict[str, dict[str, dict[str, str]]] = {}
    if not isinstance(value, Mapping):
        return found
    for provider, models in value.items():
        if not isinstance(models, Mapping):
            continue
        for model, languages in models.items():
            if not isinstance(languages, Mapping):
                continue
            kept = {
                str(language): str(voice)
                for language, voice in languages.items()
                if isinstance(voice, str) and voice.strip()
            }
            if kept:
                found.setdefault(str(provider), {})[str(model)] = kept
    return found


def _read(row: Any) -> PronunciationSettings:
    if row is None:
        return PronunciationSettings()
    return PronunciationSettings(
        pregenerate=row["pregenerate"], expressive=row["expressive"], voices=row["voices"], chosen=True
    )


def settings(owner: str) -> PronunciationSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.pronunciation_settings).where(tables.pronunciation_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(
    owner: str,
    *,
    pregenerate: Mapping[str, bool] | None = None,
    expressive: bool | None = None,
    voices: Mapping[str, Any] | None = None,
) -> PronunciationSettings:
    """Change only what is named, inside one `BEGIN IMMEDIATE`. Returns the whole stored document."""
    table = tables.pronunciation_settings
    with transaction() as connection:
        row = connection.execute(select(table).where(table.c.owner == owner)).mappings().first()
        current = _read(row)
        wanted = PronunciationSettings(
            pregenerate={**current.pregenerate, **(pregenerate or {})},
            expressive=current.expressive if expressive is None else expressive,
            voices=current.voices if voices is None else voices,
            chosen=True,
        )
        values = {
            "pregenerate": dict(wanted.pregenerate),
            "expressive": wanted.expressive,
            "voices": wanted.voices,
            "edited_at": now_instant(),
        }
        if row is None:
            connection.execute(table.insert().values(id=new_record_id(), owner=owner, **values))
        else:
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))
        return wanted

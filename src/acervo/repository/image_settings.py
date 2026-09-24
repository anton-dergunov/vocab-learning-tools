"""How this owner wants sense images drawn. One row per owner, or none — and none is a real answer.

The same three-state doctrine as `model_selection`, and for the same reason: **no record means "use
the deployment default"**. Nothing creates a row eagerly and there is no `ensure_` function, so
every read is a pure read with nothing to write when it is missing. Eager creation would have to
invent a value, and snapshotting today's default would freeze it at the instant the account was made.

These live on the server rather than on the device, unlike the editor's wrapping preference, because
the drawing happens on the server: a phone that has never opened Settings must still get the styles
the owner chose.

This module stores what it is given. Which styles exist is `config/image-styles.yaml`'s question and
`acervo.services.images` is where a document is held to it — a style id this table has never heard
of is not this module's business, exactly as a provider id is not `model_selection`'s.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.repository.session import reading, transaction

# Which stories draw their later pictures from their earlier ones: every style, every style but the
# photographic ones, or none. The first is the default, and why is on the column in `db/tables.py`.
CONTINUITY = ("all", "artwork", "off")
CONTINUITY_DEFAULT = "all"


class ImageSettings(Mapping):
    """The owner's answer, or the deployment default when they have not given one.

    A `Mapping` so a route can return it as a document without a second shape to keep in step, and
    `chosen` is what says whether a row exists — which the settings screen needs in order to show
    "following the default" rather than showing the default as though it had been picked.
    """

    __slots__ = ("draw_enabled", "styles_off", "boost_variety", "story_continuity", "chosen")

    def __init__(
        self,
        *,
        draw_enabled: bool = True,
        styles_off: Iterable[str] = (),
        boost_variety: bool = True,
        story_continuity: str = CONTINUITY_DEFAULT,
        chosen: bool = False,
    ) -> None:
        self.draw_enabled = bool(draw_enabled)
        # A tuple, sorted and de-duplicated, so two saves of the same set compare equal and a
        # hand-edited row cannot make the offered list depend on JSON key order.
        self.styles_off = tuple(sorted({str(one) for one in styles_off if str(one).strip()}))
        self.boost_variety = bool(boost_variety)
        # An unknown value reads as the default rather than raising, for `_read`'s reason below.
        self.story_continuity = story_continuity if story_continuity in CONTINUITY else CONTINUITY_DEFAULT
        self.chosen = bool(chosen)

    def __getitem__(self, key: str) -> Any:
        return {
            "drawEnabled": self.draw_enabled,
            "stylesOff": list(self.styles_off),
            "boostVariety": self.boost_variety,
            "storyContinuity": self.story_continuity,
            "chosen": self.chosen,
        }[key]

    def __iter__(self):
        return iter(("drawEnabled", "stylesOff", "boostVariety", "storyContinuity", "chosen"))

    def __len__(self) -> int:
        return 5

    def continuity_for(self, photographic: bool) -> bool:
        """Whether a story drawn in a style that is (or is not) photographic uses references."""
        return self.story_continuity == "all" or (
            self.story_continuity == "artwork" and not photographic)

    def weights(self, style_ids: Iterable[str]) -> dict[str, float]:
        """The switched-off styles as the zero weights `StyleTable.offer` already understands.

        Stored as the styles switched **off**, never the ones switched on: a set of switched-on ids
        left the online dictionary sources permanently silent when one was added later, and a style
        added to the table must be on by default. Only this direction gives that for free.
        """
        off = set(self.styles_off)
        return {style_id: 0.0 for style_id in style_ids if style_id in off}


def _read(row: Any) -> ImageSettings:
    if row is None:
        return ImageSettings()
    stored = row["styles_off"]
    return ImageSettings(
        draw_enabled=row["draw_enabled"],
        # Dropping anything malformed rather than raising: a hand-edited row must not take the
        # capture path down, and an unknown style id is harmless — it switches nothing off.
        styles_off=stored if isinstance(stored, list) else (),
        boost_variety=row["boost_variety"],
        story_continuity=row["story_continuity"],
        chosen=True,
    )


def settings(owner: str) -> ImageSettings:
    with reading() as connection:
        row = connection.execute(
            select(tables.image_settings).where(tables.image_settings.c.owner == owner)
        ).mappings().first()
    return _read(row)


def save(
    owner: str,
    *,
    draw_enabled: bool | None = None,
    styles_off: Iterable[str] | None = None,
    boost_variety: bool | None = None,
    story_continuity: str | None = None,
) -> ImageSettings:
    """Change only what is named. Returns the whole stored document, so a caller echoes disk.

    Read-modify-write inside one `transaction()`, which is `BEGIN IMMEDIATE`, so check-then-insert
    cannot interleave with a second save and the unique index is never reached in anger.

    There is deliberately no way to *forget* a row here, unlike `model_selection.save`. That
    function needs one because unchecking every model is refused as an empty chain, leaving no route
    back to the default; here every field has a value that is meaningful on its own, so following
    the deployment default is a state you have simply not left rather than one you can be trapped
    outside of.
    """
    with transaction() as connection:
        row = connection.execute(
            select(tables.image_settings).where(tables.image_settings.c.owner == owner)
        ).mappings().first()
        current = _read(row)

        wanted = ImageSettings(
            draw_enabled=current.draw_enabled if draw_enabled is None else draw_enabled,
            styles_off=current.styles_off if styles_off is None else styles_off,
            boost_variety=current.boost_variety if boost_variety is None else boost_variety,
            story_continuity=(current.story_continuity if story_continuity is None
                              else story_continuity),
            chosen=True,
        )
        values = {
            "draw_enabled": wanted.draw_enabled,
            "styles_off": list(wanted.styles_off),
            "boost_variety": wanted.boost_variety,
            "story_continuity": wanted.story_continuity,
            "edited_at": now_instant(),
        }

        if row is None:
            connection.execute(
                tables.image_settings.insert().values(
                    id=new_record_id(), owner=owner, **values
                )
            )
        else:
            connection.execute(
                tables.image_settings.update()
                .where(tables.image_settings.c.id == row["id"])
                .values(**values)
            )
        return wanted

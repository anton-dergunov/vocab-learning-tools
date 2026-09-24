"""Removing the photos nobody added: a runner tick, not a job and not a step of the nightly run.

A photo is stored the moment it is read, before anyone knows whether a word will be added from it,
and waits in `pending/` for a save to name it (`services/photo.py`). One that is still waiting after
a day was never going to be, and this removes it. It is a tick rather than a nightly step because it
is owner-independent file housekeeping with nothing to decide — a step would give the owner a switch
that means nothing, and a job would put a row in the activity list every hour.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from acervo.services import photo
from acervo.settings import Settings

log = logging.getLogger("acervo.work")

SWEEP_EVERY_SECONDS = 60 * 60


def timer(settings: Settings, clock: Callable[[], float]) -> Callable[[], None]:
    """The runner tick that sweeps pending photos. Looks at most once an hour."""
    last: list[float] = []

    def tick() -> None:
        now = clock()
        if last and now - last[0] < SWEEP_EVERY_SECONDS:
            return
        last[:] = [now]
        removed = photo.sweep(settings)
        if removed:
            log.info("removed %d photo(s) nobody added", removed)

    return tick

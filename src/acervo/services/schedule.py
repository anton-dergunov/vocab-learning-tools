"""When the nightly run happens: one hour, one switch per step (`docs/architecture/jobs.md`).

One timer rather than one per job: steps in sequence can never start together or compete for the
same allowance, so nothing needs an offset. The hour is read in `ACERVO_TIMEZONE`, or the server's
own zone when that is unset.

When a run is due is the runner's question (`work/nightly.py`), since it reads the job record.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from acervo.domain.ids import instant_of
from acervo.errors import ApiError
from acervo.repository import schedule_settings
from acervo.repository.schedule_settings import STEPS
from acervo.settings import Settings

# Steps that are declared but cannot run from here yet. Refused when switched on, rather than
# accepted and then failed every night.
UNAVAILABLE = {
    "anki.pull": "Pulling Anki's review state still runs from the worker "
                 "(run-worker.sh pull-state), so it cannot be scheduled here yet.",
}


def zone(settings: Settings) -> tzinfo:
    if settings.timezone:
        try:
            return ZoneInfo(settings.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def zone_name(settings: Settings) -> str:
    local = zone(settings)
    return getattr(local, "key", None) or datetime.now(local).tzname() or "UTC"


def last_scheduled(settings: Settings, hour: int, now: datetime) -> datetime:
    """The most recent moment the nightly hour struck, at or before `now`, in UTC."""
    local = now.astimezone(zone(settings))
    struck = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if struck > local:
        struck = (struck - timedelta(days=1)).replace(hour=hour)
    return struck.astimezone(timezone.utc)


def next_scheduled(settings: Settings, hour: int, now: datetime) -> datetime:
    local = last_scheduled(settings, hour, now).astimezone(zone(settings))
    return (local + timedelta(days=1)).replace(hour=hour).astimezone(timezone.utc)


def settings_view(settings: Settings, owner: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    chosen = schedule_settings.settings(owner)
    return {
        **chosen,
        "timezone": zone_name(settings),
        "nextRunAt": instant_of(next_scheduled(settings, chosen.hour, now)),
        "unavailable": dict(UNAVAILABLE),
    }


def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    hour = body.get("hour")
    if hour is not None and (isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23):
        raise ApiError(400, "invalid_input", "The hour is a whole number from 0 to 23.")
    steps = body.get("steps")
    if steps is not None:
        if not isinstance(steps, dict) or any(
            name not in STEPS or not isinstance(value, bool) for name, value in steps.items()
        ):
            raise ApiError(
                400, "invalid_input", f"The nightly steps are {', '.join(STEPS)}, each on or off."
            )
        for name, value in steps.items():
            if value and name in UNAVAILABLE:
                raise ApiError(409, "step_unavailable", UNAVAILABLE[name])
    schedule_settings.save(owner, hour=hour, steps=steps)
    return settings_view(settings, owner)

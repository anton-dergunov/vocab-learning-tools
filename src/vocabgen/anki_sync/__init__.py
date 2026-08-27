"""Headless Anki synchronization for Acervo-rendered study material."""

from typing import Any

from .manifest import SyncManifest, SyncManifestNote

__all__ = ["AnkiRobot", "RobotSettings", "SyncManifest", "SyncManifestNote"]


def __getattr__(name: str) -> Any:
    if name in {"AnkiRobot", "RobotSettings"}:
        from .robot import AnkiRobot, RobotSettings

        return {"AnkiRobot": AnkiRobot, "RobotSettings": RobotSettings}[name]
    raise AttributeError(name)

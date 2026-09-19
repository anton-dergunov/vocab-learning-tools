"""Creating the schema, and refusing to serve one that is not this one.

Alembic defines and bootstraps the schema. It is **not** an upgrade path: one head, and *rebuild the
database* is the default way a schema change is deployed. Offering `alembic upgrade head` as a
second, untested path against real data would be a promise nobody has decided to keep.

A purely additive change may instead be carried across by a throwaway converter that creates the new
tables and re-stamps the head by hand — outside the application, deleted once it has run, so nothing
here learns that an earlier version existed. The guard below is what makes that safe rather than
hopeful: a database nobody has converted is refused by name rather than served.

What the stamp buys is the failure this replaces. A database predating a schema rewrite used to make
every graph route fail with an anonymous 500 that the client reported as "offline" — a long way from
"this database must be rebuilt". `bootstrap` says which it is.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

ALEMBIC_PATH = Path(__file__).resolve().parent / "alembic"


class SchemaOutOfDate(RuntimeError):
    """The database on disk was written under a different schema, and must be rebuilt."""


def _config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_PATH))
    # `env.py` runs against this rather than opening a second connection of its own.
    config.attributes["engine"] = engine
    return config


def head_revision() -> str | None:
    return ScriptDirectory(str(ALEMBIC_PATH)).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def bootstrap(engine: Engine) -> None:
    """Create the schema when this database is empty; refuse it when it is somebody else's."""
    head = head_revision()
    stamped = current_revision(engine)
    if stamped == head:
        return
    if stamped is None and not inspect(engine).has_table("users"):
        command.upgrade(_config(engine), "head")
        return
    raise SchemaOutOfDate(
        f"The Acervo database is at schema revision {stamped or 'none'}, but this server expects "
        f"{head}. Development databases and incompatible replicas are disposable: redeploy with "
        f"--reset-database to rebuild it."
    )

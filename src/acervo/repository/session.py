"""The process's engine, and the two ways to reach it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, Engine

from acervo.db.bootstrap import bootstrap
from acervo.db.engine import create_database_engine

_engine: Engine | None = None


def use(engine: Engine) -> None:
    global _engine
    _engine = engine


def open_database(path: Path) -> Engine:
    """Create, bootstrap and install the engine this process will use."""
    engine = create_database_engine(path)
    bootstrap(engine)
    use(engine)
    return engine


def engine() -> Engine:
    if _engine is None:
        raise RuntimeError("No Acervo database is configured for this process.")
    return _engine


@contextmanager
def transaction() -> Iterator[Connection]:
    """One write, all of it or none of it. Emits `BEGIN IMMEDIATE` through the engine listener."""
    with engine().begin() as connection:
        yield connection


@contextmanager
def reading() -> Iterator[Connection]:
    """A pure read, taking no write lock.

    `GET /graph` is the most frequent request in the system — once every 60 seconds per visible
    client — and it must not queue behind or in front of a write. AUTOCOMMIT is what keeps SQLAlchemy
    from autobeginning, which would otherwise fire the `BEGIN IMMEDIATE` listener and take the
    database's single write slot to answer a poll.
    """
    with engine().connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        yield connection

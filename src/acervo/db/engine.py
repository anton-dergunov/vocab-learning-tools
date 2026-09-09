"""The engine, and the five connection settings each of which is silently wrong if omitted."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event


def create_database_engine(path: Path, *, echo: bool = False) -> Engine:
    """An engine for the Acervo core, configured the way SQLite has to be configured for this load."""
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        echo=echo,
        # FastAPI runs synchronous endpoints in a thread pool, so a connection is not bound to the
        # thread that opened it.
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection, _record):  # pragma: no cover - exercised by every test
        # Hand transaction control to us. Left alone, pysqlite emits its own BEGIN at a moment of its
        # choosing, and the `begin` listener below would never get to say which kind.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # Readers do not block the writer.
        cursor.execute("PRAGMA journal_mode=WAL")
        # WAL's companion; FULL buys an fsync per commit for nothing at this write rate.
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Ordinary contention.
        cursor.execute("PRAGMA busy_timeout=5000")
        # Defaults off, and is per-connection. Without this every foreign key in the schema is
        # decorative.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):  # pragma: no cover - exercised by every write
        # Under WAL a deferred transaction that reads and then writes fails its lock upgrade with
        # SQLITE_BUSY *immediately* — the busy handler is not invoked for an upgrade, so
        # `busy_timeout` does not save you. The revision counter reads-then-writes on every single
        # write, so this is not a corner case.
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine

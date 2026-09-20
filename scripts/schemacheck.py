"""Whether a database on disk is the one the code would create, table by table.

The comparison a schema converter needs twice: before it writes, to prove the change really is the
narrow one it was written for, and after, to prove it landed. `transition.py` runs it after every
conversion whatever the converter did, so a converter cannot report success it did not achieve.

Nothing that ships imports this. It lives beside the scripts that use it and is copied into a release
with them, and it knows nothing about any particular schema change.
"""

from __future__ import annotations

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Engine


def columns(table, dialect) -> dict[str, str]:
    """Each column as `name -> type:nullability:key`, compiled to the dialect.

    Deliberately **not** `shape_of` from the bootstrap migration. That one reads SQLAlchemy type
    objects (`String(15)`), and a table reflected back out of SQLite carries the dialect's own
    (`VARCHAR(15)`) — so comparing the two would report every column of every table as changed. The
    types are compiled on both sides here, which is the comparison actually wanted: *is the table on
    disk the one this code would create*.
    """
    return {
        column.name: f"{column.type.compile(dialect)}"
                     f":{'null' if column.nullable else 'notnull'}"
                     f"{':pk' if column.primary_key else ''}"
        for column in table.columns
    }


def indexes(table) -> dict[str, str]:
    return {
        index.name: f"({','.join(sorted(c.name for c in index.columns))})"
                    f"{':unique' if index.unique else ''}"
        for index in table.indexes
    }


def differences(name: str, want, have, dialect) -> list[str]:
    """Every way one table on disk differs from the code, **named one at a time**.

    A dump of both descriptions side by side is technically the same information and useless in
    practice: the reader is left diffing two 24-column strings by eye, at the exact moment they have
    been told something is wrong with their database. Each difference gets its own line.
    """
    found: list[str] = []
    for label, code, disk in (
        ("column", columns(want, dialect), columns(have, dialect)),
        ("index", indexes(want), indexes(have)),
    ):
        for key in sorted(set(code) - set(disk)):
            found.append(f"{name}: {label} {key!r} is in the code but not the database")
        for key in sorted(set(disk) - set(code)):
            found.append(f"{name}: {label} {key!r} is in the database but not the code")
        for key in sorted(set(code) & set(disk)):
            if code[key] != disk[key]:
                found.append(f"{name}: {label} {key!r} is {disk[key]} on disk, {code[key]} in code")
    return found


def stamped(engine: Engine) -> str | None:
    """The revision the database says it is at, or None if it says nothing."""
    with engine.connect() as connection:
        if not inspect(engine).has_table("alembic_version"):
            return None
        row = connection.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None


def compare(engine: Engine, metadata: MetaData, names: list[str]) -> list[str]:
    """Every way the database differs from what the code declares, for these tables."""
    reflected = MetaData()
    reflected.reflect(bind=engine, only=names)
    problems: list[str] = []
    for name in names:
        on_disk = reflected.tables.get(name)
        if on_disk is None:
            problems.append(f"{name}: the table is missing from the database")
            continue
        problems.extend(differences(name, metadata.tables[name], on_disk, engine.dialect))
    return problems

"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that added `stories`,
`story_parts` and `story_words` — and it exists so that ~1,500 words, their pictures and their
recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
hand, and deleted. A script still here two schema changes from now has become the compatibility
layer the rule forbids.

**Why this change can be carried at all.** The head revision id is a digest of the whole schema, so
any change moves it and `db/bootstrap.py` then refuses to serve a database stamped with the old one.
Usually the remedy is `--reset-database`. Here it does not have to be, because the change is *purely
additive*: three new tables, and not one existing column, index or constraint altered. The database
on disk is therefore already shaped correctly for every table the old code knew about, and all that
stands between it and the new head is three `CREATE TABLE`s and a stamp.

**What makes that honest rather than hopeful is that the script checks rather than assumes.** It
compares every pre-existing table on disk against what the code declares, and refuses — naming what
differs — if anything but the three new tables has moved. If that check fails, this script is the
wrong tool and `--reset-database` is the answer.

Run it with the server stopped, on a copy you have taken first:

    cp /var/lib/acervo/server/acervo.db ~/acervo-backup.db
    python scripts/throwaway/add_story_tables.py --database /var/lib/acervo/server/acervo.db \
        --from-revision bootstrap_194ba25327ce

`--dry-run` does every check and writes nothing, which is what to run first.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

# The three this script adds. Everything else must already be there and must already match.
ADDED = ("stories", "story_parts", "story_words")


def _columns(table, dialect) -> dict[str, str]:
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


def _indexes(table) -> dict[str, str]:
    return {
        index.name: f"({','.join(sorted(c.name for c in index.columns))})"
                    f"{':unique' if index.unique else ''}"
        for index in table.indexes
    }


def _differences(name: str, want, have, dialect) -> list[str]:
    """Every way one table on disk differs from the code, **named one at a time**.

    A dump of both descriptions side by side is technically the same information and useless in
    practice: the reader is left diffing two 24-column strings by eye, at the exact moment they have
    been told something is wrong with their database. Each difference gets its own line.
    """
    found: list[str] = []
    for label, code, disk in (
        ("column", _columns(want, dialect), _columns(have, dialect)),
        ("index", _indexes(want), _indexes(have)),
    ):
        for key in sorted(set(code) - set(disk)):
            found.append(f"{name}: {label} {key!r} is in the code but not the database")
        for key in sorted(set(disk) - set(code)):
            found.append(f"{name}: {label} {key!r} is in the database but not the code")
        for key in sorted(set(code) & set(disk)):
            if code[key] != disk[key]:
                found.append(f"{name}: {label} {key!r} is {disk[key]} on disk, {code[key]} in code")
    return found


def _stamped(engine: Engine) -> str | None:
    with engine.connect() as connection:
        if not inspect(engine).has_table("alembic_version"):
            return None
        row = connection.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None


def _compare(engine: Engine, names: list[str]) -> list[str]:
    """Every way the database differs from what the code declares, for these tables."""
    reflected = MetaData()
    reflected.reflect(bind=engine, only=names)
    dialect = engine.dialect
    problems: list[str] = []
    for name in names:
        on_disk = reflected.tables.get(name)
        if on_disk is None:
            problems.append(f"{name}: the table is missing from the database")
            continue
        problems.extend(_differences(name, metadata.tables[name], on_disk, dialect))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="the acervo.db to convert")
    parser.add_argument(
        "--from-revision", required=True,
        help="the head this database must currently be stamped with; refuses any other",
    )
    parser.add_argument("--dry-run", action="store_true", help="check everything, write nothing")
    args = parser.parse_args()

    if not args.database.exists():
        print(f"There is no database at {args.database}.", file=sys.stderr)
        return 2

    engine = create_engine(f"sqlite+pysqlite:///{args.database}")
    stamped = _stamped(engine)

    if stamped == HEAD:
        print(f"Already at {HEAD}. Nothing to do.")
        return 0
    # Refused by name, and in both directions: a database stamped with anything but the one head
    # this script was written against is one it has not been reasoned about, and guessing is exactly
    # what a converter must not do.
    if stamped != args.from_revision:
        print(
            f"This database is stamped {stamped or 'nothing'}, not {args.from_revision}.\n"
            "This script converts one specific schema change and refuses any other. Rebuild with "
            "./deploy.sh --reset-database instead.",
            file=sys.stderr,
        )
        return 2

    existing = [name for name in metadata.tables if name not in ADDED]
    problems = _compare(engine, sorted(existing))
    if problems:
        print(
            "This change is only safe because nothing existing was altered, and something was:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    already = [name for name in ADDED if inspect(engine).has_table(name)]
    if already:
        print(f"Refusing: {', '.join(already)} already exist(s) but the head has not moved.",
              file=sys.stderr)
        return 2

    print(f"{len(existing)} existing tables match the code exactly.")
    print(f"Adding: {', '.join(ADDED)}")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    metadata.create_all(engine, tables=[metadata.tables[name] for name in ADDED])
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = _compare(engine, sorted(metadata.tables))
    if remaining or _stamped(engine) != HEAD:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(remaining), file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    print("Start the server, then delete this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

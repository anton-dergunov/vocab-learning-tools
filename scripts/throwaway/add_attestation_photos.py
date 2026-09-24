"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave `attestations`
two columns, `photo_ref` and `photo_region`, so a word captured from a photo keeps the photo — and it
exists so that the owner's words, pictures, recordings, loops and stories are not rebuilt along with
the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

**Why this change can be carried at all.** The head revision id is a digest of the whole schema, so
any change moves it and `db/bootstrap.py` then refuses to serve a database stamped with the old one.
Here the change is *purely additive*: two new columns, one with a default and one nullable, and not
one existing column, index or constraint altered. Every existing attestation reads as one that was
typed or pasted, which is what it was.

**What makes that honest rather than hopeful is that the script checks rather than assumes.** It
compares every table on disk against what the code declares and refuses — naming what differs — if
anything but those two columns has moved. If that check fails, this script is the wrong tool and
`--reset-database` is the answer.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real,
and afterwards checks the whole schema again whatever this script said. To run it alone, on a copy you
have taken first, with the server stopped:

    python scripts/throwaway/add_attestation_photos.py --database PATH --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

# The one head this converts *from*. `transition.py` reads it to choose this script.
FROM_REVISION = "bootstrap_8020b0d32802"

TABLE = "attestations"
# Each column as SQLite is told to add it. An explicit DDL default for the NOT NULL one, because
# SQLAlchemy's `default=` is applied in Python and SQLite refuses to add a NOT NULL column that has
# none. `""` is what "no photo" is stored as; `photo_region` is simply null.
COLUMNS = {
    "photo_ref": "VARCHAR(500) NOT NULL DEFAULT ''",
    "photo_region": "JSON",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--database", required=True, type=Path, help="the acervo.db to convert")
    parser.add_argument("--dry-run", action="store_true", help="check everything, write nothing")
    args = parser.parse_args(argv)

    if not args.database.exists():
        print(f"There is no database at {args.database}.", file=sys.stderr)
        return 2

    engine = create_engine(f"sqlite+pysqlite:///{args.database}")
    stamped = schemacheck.stamped(engine)

    if stamped == HEAD:
        print(f"Already at {HEAD}. Nothing to do.")
        return 0
    # Refused by name: a database stamped with anything but the one head this script was written
    # against is one it has not been reasoned about, and guessing is what a converter must not do.
    if stamped != FROM_REVISION:
        print(
            f"This database is stamped {stamped or 'nothing'}, not {FROM_REVISION}.\n"
            "This script converts one specific schema change and refuses any other. Rebuild with "
            "./deploy.sh --reset-database instead.",
            file=sys.stderr,
        )
        return 2

    others = sorted(name for name in metadata.tables if name != TABLE)
    problems = schemacheck.compare(engine, metadata, others)
    changed = schemacheck.compare(engine, metadata, [TABLE])
    missing = {
        f"{TABLE}: column {column!r} is in the code but not the database": column for column in COLUMNS
    }
    # Acceptable: some of the two columns are missing and nothing else differs. "Some" rather than
    # "both", because the columns are added one statement at a time and an interrupted earlier run
    # leaves the first in place — adding it a second time would fail rather than finish the job.
    problems.extend(change for change in changed if change not in missing)
    if problems:
        print(
            "This change is only safe because nothing but two columns was added, and something else "
            "moved:\n  " + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    adding = [missing[change] for change in changed]
    print(f"{len(others)} other tables match the code exactly.")
    for column in COLUMNS:
        print(f"Adding: {TABLE}.{column}" if column in adding else f"{TABLE}.{column} is already there.")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        for column in adding:
            connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {column} {COLUMNS[column]}"))
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": HEAD})

    # Verified against the *whole* new schema, so the script proves what it claims rather than
    # reporting that it finished.
    remaining = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    if remaining or schemacheck.stamped(engine) != HEAD or not inspect(engine).has_table(TABLE):
        print("The conversion did not land cleanly:\n  " + "\n  ".join(remaining), file=sys.stderr)
        return 1

    print(f"\nDone. All {len(metadata.tables)} tables match, stamped {HEAD}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

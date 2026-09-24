"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that gave `image_settings`
the `story_continuity` column, which says whether a story's later pictures are drawn with its earlier
ones as references — and it exists so that the owner's words, pictures, recordings and stories are
not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

**Why this change can be carried at all.** The head revision id is a digest of the whole schema, so
any change moves it and `db/bootstrap.py` then refuses to serve a database stamped with the old one.
Here it does not have to mean `--reset-database`, because the change is *purely additive*: one new
column with a default on one table, and not one existing column, index or constraint altered. An
owner who saved picture settings before this reads as the default, `artwork`.

**What makes that honest rather than hopeful is that the script checks rather than assumes.** It
compares every table on disk against what the code declares and refuses — naming what differs — if
anything but that column has moved.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real,
and afterwards checks the whole schema again whatever this script said. To run it alone, on a copy you
have taken first, with the server stopped:

    python scripts/throwaway/add_story_continuity.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_203766d3cba6"

TABLE = "image_settings"
# An explicit DDL default, because SQLAlchemy's `default=` is applied in Python and SQLite refuses to
# add a NOT NULL column that has none.
COLUMNS = {
    "story_continuity": "VARCHAR(16) NOT NULL DEFAULT 'artwork'",
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
    missing = [f"{TABLE}: column {name!r} is in the code but not the database" for name in COLUMNS]
    # Two states are acceptable. Either the column is the one thing missing, or it is already there
    # and only the stamp did not move — which is what an interrupted earlier run leaves, and adding
    # it a second time would fail rather than finish the job.
    if sorted(changed) not in (sorted(missing), []):
        problems.extend(change for change in changed if change not in missing)
    if problems:
        print(
            "This change is only safe because nothing but that column was added, and something else moved:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    add_columns = sorted(changed) == sorted(missing)
    print(f"{len(others)} other tables match the code exactly.")
    print(f"Adding: {TABLE}.({', '.join(COLUMNS)})" if add_columns else f"{TABLE}'s column is already there.")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        if add_columns:
            for name, definition in COLUMNS.items():
                connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {definition}"))
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

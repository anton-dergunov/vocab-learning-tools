"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that added
`prompt_rules`, the owner's standing rules for generated text — and it exists so that the owner's
words, pictures and recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

The change is purely additive: one new table, empty, and nothing existing altered. So the whole
conversion is creating it and re-stamping the head, and every other table is checked first to be
exactly what the code expects.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real,
and afterwards checks the whole schema again whatever this script said. To run it alone, on a copy you
have taken first, with the server stopped:

    python scripts/throwaway/add_prompt_rules.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_a3dfce37b4e3"

TABLE = "prompt_rules"


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
    if problems:
        print(
            "This change only adds one table, and something else has moved:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    present = inspect(engine).has_table(TABLE)
    print(f"{len(others)} other tables match the code exactly.")
    print(f"Creating: {TABLE}" + (" (already there)" if present else ""))
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        # The table exactly as the code declares it, index included, so the check below compares
        # like with like rather than with a hand-written copy.
        metadata.tables[TABLE].create(connection, checkfirst=True)
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

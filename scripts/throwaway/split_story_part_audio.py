"""**A throwaway script. Delete it once it has run.**

It carries one Acervo database across one specific schema change — the one that stopped storing a
story part's narration as a single joined file and started storing **one file per passage** — and it
exists so that the owner's words, pictures and recordings are not rebuilt along with the schema.

Nothing that ships imports this. It is the way out named in AGENTS.md, "Backward compatibility stays
out of the shipped code": a converter outside the application, written for one transition, run by
`./deploy.sh --transition`, and deleted afterwards. A script still here two schema changes from now
has become the compatibility layer the rule forbids — and `FROM_REVISION` below will by then match no
database at all, which is how a stale one announces itself.

**What it does to the narration, and why it cannot do better.** The old shape was one recording per
part with the passages' times written beside it; the new one is a file per passage. Splitting the old
file at those times would be sound processing in a throwaway script, and the times are exactly what
was not to be trusted — a browser seeks a compressed stream to a page boundary, which is the defect
the change exists to remove. So **every story part is returned to "not recorded"** and the narration
is made again, which costs model calls and nothing else: the words, the translations, the pictures
and every other record are untouched. The superseded audio files are left on the media volume; they
are named by rows that no longer exist, and `story-audio-*.ogg` under `media/stories/` can be removed
by hand at any time.

`transition.py` picks this script by `FROM_REVISION`, runs it once with `--dry-run` and then for real,
and afterwards checks the whole schema again whatever this script said. To run it alone, on a copy you
have taken first, with the server stopped:

    python scripts/throwaway/split_story_part_audio.py --database PATH --dry-run
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
FROM_REVISION = "bootstrap_789853e4a9d4"

TABLE = "story_parts"
# The two columns that go: a part no longer has a recording of its own, only passages that do.
DROPPED = ("audio_ref", "audio_mime")


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
            "This change touches one table, and something else has moved:\n  "
            + "\n  ".join(problems)
            + "\n\nThis script is the wrong tool. Rebuild with ./deploy.sh --reset-database.",
            file=sys.stderr,
        )
        return 2

    held = {row[1] for row in engine.connect().execute(text(f"PRAGMA table_info({TABLE})"))}
    going = [name for name in DROPPED if name in held]
    with engine.connect() as connection:
        recorded = connection.execute(
            text(f"SELECT COUNT(*) FROM {TABLE} WHERE audio_segments NOT IN ('[]', '')")
        ).scalar() or 0

    print(f"{len(others)} other tables match the code exactly.")
    print(f"Dropping: {', '.join(f'{TABLE}.{name}' for name in going) or '(already gone)'}")
    print(f"Returning {recorded} story parts to 'not recorded'; their narration is made again.")
    print(f"Stamp:  {stamped} → {HEAD}")
    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    with engine.begin() as connection:
        # The passages and the pair that spoke them go together: the validator refuses a part that
        # names who read it but has no passages, so half of this would leave unwritable rows.
        connection.execute(text(
            f"UPDATE {TABLE} SET audio_segments = '[]', audio_provider_id = '', "
            f"audio_model_id = '', audio_voice = ''"
        ))
        for name in going:
            connection.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {name}"))
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

"""Carries an Acervo database across a schema change, by finding the converter written for it.

`./deploy.sh --transition` runs this inside the new server image, after taking a backup and before
the new server starts. It takes no argument naming a converter: it reads the revision the database
is stamped with and looks for the one file under `scripts/throwaway/` that says it converts *from*
that revision (`FROM_REVISION`). Then:

  * a database already at this release's revision has nothing to convert, and this succeeds;
  * a database at a revision some converter names is dry-run through it and then converted, and the
    whole schema is checked afterwards whatever the converter reported;
  * anything else is refused, naming both revisions — the server would refuse it too, and the remedy
    is `./deploy.sh --reset-database`.

**Revisions are digests, not versions**, so they have no order and "newer than this release" cannot
be recognised: a database from the future looks exactly like one from the past that nobody wrote a
converter for. Both are refused, which is the only honest answer.

This knows nothing about what any converter does, and a converter knows nothing about this beyond
two names — `FROM_REVISION` and `main(argv)`, taking `--database` and `--dry-run`. Deleting a
converter therefore leaves nothing behind here, and the deployment code never learns an earlier
version existed. Not a throwaway itself: it is the mechanism, and it ships with the release.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

THROWAWAY = Path(__file__).resolve().parent / "throwaway"


def converters(directory: Path) -> list[tuple[str, ModuleType]]:
    """Every converter in the directory, as `(file name, module)`. One that will not load is fatal:
    a converter that silently drops out is how the wrong one, or none, gets picked."""
    found: list[tuple[str, ModuleType]] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"acervo_transition_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ("FROM_REVISION", "main"):
            if not hasattr(module, name):
                raise SystemExit(f"{path.name} is not a converter: it has no {name}.")
        found.append((path.name, module))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--database", type=Path, default=os.environ.get("ACERVO_DB_PATH"),
        help="the acervo.db to convert (default: $ACERVO_DB_PATH)",
    )
    parser.add_argument("--throwaway-dir", type=Path, default=THROWAWAY, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.database is None:
        print("There is no database to convert: pass --database or set ACERVO_DB_PATH.", file=sys.stderr)
        return 2
    if not args.database.exists():
        # A first deployment. The server creates its own database at the current head.
        print(f"There is no database at {args.database} yet, so there is nothing to convert.")
        return 0

    engine = create_engine(f"sqlite+pysqlite:///{args.database}")
    stamped = schemacheck.stamped(engine)
    if stamped == HEAD:
        print(f"The database is already at {HEAD}. Nothing to convert.")
        return 0

    available = converters(args.throwaway_dir) if args.throwaway_dir.is_dir() else []
    matching = [(name, module) for name, module in available if module.FROM_REVISION == stamped]
    if stamped is None or not matching:
        print(
            f"This database is stamped {stamped or 'nothing'}, and this release expects {HEAD}.\n"
            f"There is no converter for {stamped or 'that'}"
            + (f" (the converters here are for: {', '.join(m.FROM_REVISION for _, m in available)})"
               if available else " (there are no converters in this release)")
            + ".\nRebuild with ./deploy.sh --reset-database instead.",
            file=sys.stderr,
        )
        return 2
    if len(matching) > 1:
        print(
            f"More than one converter claims {stamped}: {', '.join(name for name, _ in matching)}. "
            "Delete the ones that have already run.",
            file=sys.stderr,
        )
        return 2

    name, module = matching[0]
    print(f"The database is at {stamped}; this release expects {HEAD}.")
    print(f"Converting with {name}.\n")

    arguments = ["--database", str(args.database)]
    print("Dry run:")
    code = module.main([*arguments, "--dry-run"])
    if code != 0:
        print("\nThe dry run refused, so nothing was written.", file=sys.stderr)
        return code
    print("\nConverting:")
    code = module.main(arguments)
    if code != 0:
        return code

    # Whatever the converter said, the schema is checked here: this is what the server will hold it
    # to when it starts, and a converter cannot vouch for itself.
    problems = schemacheck.compare(engine, metadata, sorted(metadata.tables))
    if problems or schemacheck.stamped(engine) != HEAD:
        print("The conversion did not land cleanly:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"\nConverted. Once you have seen the new server working, delete scripts/throwaway/{name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

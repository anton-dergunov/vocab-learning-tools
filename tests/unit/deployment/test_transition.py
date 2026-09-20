"""`scripts/transition.py`: choosing and running the converter for a database's schema.

Everything here uses converters written in a temporary directory, never a real one under
`scripts/throwaway/`. The mechanism has to keep working after every real converter has been deleted,
which is the point of it, and a test that named one would fail the day it was.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402

_spec = importlib.util.spec_from_file_location("transition_under_test", ROOT / "scripts" / "transition.py")
transition = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transition)

OLD = "bootstrap_000000000000"
OTHER = "bootstrap_ffffffffffff"


def database(tmp_path: Path, stamp: str | None = HEAD) -> Path:
    """A real database of the current schema, stamped as asked (or not at all)."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    transition.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        if stamp is not None:
            connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"), {"stamp": stamp})
    engine.dispose()
    return path


def stamp_of(path: Path) -> str | None:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        return schemacheck.stamped(engine)
    finally:
        engine.dispose()


def converter(directory: Path, name: str, *, source: str, log: Path, behaviour: str = "convert") -> None:
    """A converter that logs each call and then does what `behaviour` says.

    `convert` restamps to the head, as a real one ends up doing; `pretend` reports success and
    changes nothing; `refuse` fails its dry run.
    """
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(
        "import argparse, sqlite3\n"
        "from acervo.db.alembic.versions.bootstrap import revision as HEAD\n"
        f"FROM_REVISION = {source!r}\n"
        "def main(argv=None):\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--database')\n"
        "    parser.add_argument('--dry-run', action='store_true')\n"
        "    args = parser.parse_args(argv)\n"
        f"    open({str(log)!r}, 'a').write(('dry ' if args.dry_run else 'real ') + {name!r} + '\\n')\n"
        f"    if {behaviour!r} == 'refuse' and args.dry_run:\n"
        "        return 2\n"
        f"    if {behaviour!r} == 'convert' and not args.dry_run:\n"
        "        connection = sqlite3.connect(args.database)\n"
        "        connection.execute('UPDATE alembic_version SET version_num = ?', (HEAD,))\n"
        "        connection.commit()\n"
        "    return 0\n",
        encoding="utf-8",
    )


def run(path: Path, directory: Path) -> int:
    return transition.main(["--database", str(path), "--throwaway-dir", str(directory)])


def test_a_database_that_does_not_exist_yet_has_nothing_to_convert(tmp_path, capsys):
    """A first deployment: the server makes its own database at the current head."""
    assert run(tmp_path / "missing.db", tmp_path / "converters") == 0
    assert "nothing to convert" in capsys.readouterr().out


def test_a_database_already_at_this_release_is_left_alone(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OLD, log=log)
    path = database(tmp_path)

    assert run(path, tmp_path / "converters") == 0

    assert "already at" in capsys.readouterr().out
    assert not log.exists(), "no converter ran"


def test_the_converter_that_names_the_stamped_revision_is_run_dry_first_and_then_for_real(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "wrong.py", source=OTHER, log=log)
    converter(tmp_path / "converters", "right.py", source=OLD, log=log)
    path = database(tmp_path, OLD)

    assert run(path, tmp_path / "converters") == 0

    assert log.read_text().splitlines() == ["dry right.py", "real right.py"]
    assert stamp_of(path) == HEAD
    output = capsys.readouterr().out
    assert "Converting with right.py" in output
    assert "delete scripts/throwaway/right.py" in output, "it says which script to remove"


def test_a_database_no_converter_names_is_refused_naming_both_revisions(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OTHER, log=log)
    path = database(tmp_path, OLD)

    assert run(path, tmp_path / "converters") == 2

    error = capsys.readouterr().err
    assert OLD in error and HEAD in error
    assert OTHER in error, "and what the converters that are here are for"
    assert "--reset-database" in error
    assert not log.exists()
    assert stamp_of(path) == OLD, "nothing was written"


def test_a_release_with_no_converters_says_so_rather_than_naming_none(tmp_path, capsys):
    path = database(tmp_path, OLD)
    assert run(path, tmp_path / "no-such-directory") == 2
    assert "there are no converters in this release" in capsys.readouterr().err


def test_a_database_with_no_stamp_is_not_guessed_at(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OLD, log=log)
    path = database(tmp_path, None)

    assert run(path, tmp_path / "converters") == 2

    assert "stamped nothing" in capsys.readouterr().err
    assert not log.exists()


def test_a_converter_whose_dry_run_refuses_never_gets_to_write(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OLD, log=log, behaviour="refuse")
    path = database(tmp_path, OLD)

    assert run(path, tmp_path / "converters") == 2

    assert log.read_text().splitlines() == ["dry a.py"], "the real run never happened"
    assert stamp_of(path) == OLD
    assert "nothing was written" in capsys.readouterr().err


def test_a_converter_that_claims_success_it_did_not_achieve_is_caught(tmp_path, capsys):
    """The schema is checked afterwards whatever the converter said, because the server will hold the
    database to exactly that check and a converter cannot vouch for itself."""
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OLD, log=log, behaviour="pretend")
    path = database(tmp_path, OLD)

    assert run(path, tmp_path / "converters") == 1

    assert "did not land cleanly" in capsys.readouterr().err


def test_two_converters_for_one_revision_is_an_error_and_not_a_coin_toss(tmp_path, capsys):
    log = tmp_path / "log"
    converter(tmp_path / "converters", "a.py", source=OLD, log=log)
    converter(tmp_path / "converters", "b.py", source=OLD, log=log)
    path = database(tmp_path, OLD)

    assert run(path, tmp_path / "converters") == 2

    assert "a.py, b.py" in capsys.readouterr().err
    assert not log.exists()


def test_a_file_that_is_not_a_converter_stops_the_run(tmp_path):
    (tmp_path / "converters").mkdir()
    (tmp_path / "converters" / "notes.py").write_text("x = 1\n")
    path = database(tmp_path, OLD)

    with pytest.raises(SystemExit, match="not a converter"):
        run(path, tmp_path / "converters")

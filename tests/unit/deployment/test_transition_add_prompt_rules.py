"""The one-off converter that added `prompt_rules`.

**Delete this file together with `scripts/throwaway/add_prompt_rules.py`**, once that has run. It is
tested against a database built the way the owner's was — the current schema without the new table,
stamped with the head from before it, with a word in it — because the point of a converter is that
everything else survives it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import schemacheck  # noqa: E402
from acervo.db.alembic.versions.bootstrap import revision as HEAD  # noqa: E402
from acervo.db.tables import metadata  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_prompt_rules", ROOT / "scripts" / "throwaway" / "add_prompt_rules.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)


def _row(table, **overrides) -> dict:
    row = {}
    for column in table.columns:
        if column.name in overrides:
            row[column.name] = overrides[column.name]
        elif column.nullable:
            continue
        elif "JSON" in str(column.type):
            row[column.name] = []
        elif "INT" in str(column.type).upper() or "BOOL" in str(column.type).upper():
            row[column.name] = 1
        else:
            row[column.name] = "x"
    return row


@pytest.fixture
def old(tmp_path) -> Path:
    """The owner's database as it was: every table but the new one, and one account in it."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(engine, tables=[t for n, t in metadata.tables.items() if n != converter.TABLE])
    with engine.begin() as connection:
        users = metadata.tables["users"]
        connection.execute(users.insert().values(_row(users, id="owner0000000001")))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _engine(path: Path):
    return create_engine(f"sqlite+pysqlite:///{path}")


def test_it_adds_the_table_keeps_the_rest_and_restamps(old):
    assert converter.main(["--database", str(old)]) == 0

    engine = _engine(old)
    assert schemacheck.stamped(engine) == HEAD
    assert inspect(engine).has_table(converter.TABLE)
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1


def test_a_dry_run_writes_nothing(old, capsys):
    assert converter.main(["--database", str(old), "--dry-run"]) == 0

    assert "nothing was written" in capsys.readouterr().out
    engine = _engine(old)
    assert schemacheck.stamped(engine) == converter.FROM_REVISION
    assert not inspect(engine).has_table(converter.TABLE)


def test_running_it_twice_is_harmless(old, capsys):
    assert converter.main(["--database", str(old)]) == 0
    assert converter.main(["--database", str(old)]) == 0
    assert "Nothing to do" in capsys.readouterr().out


def test_it_refuses_a_database_stamped_with_any_other_revision_naming_both(old, capsys):
    with _engine(old).begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))

    assert converter.main(["--database", str(old)]) == 2

    error = capsys.readouterr().err
    assert "bootstrap_000000000000" in error and converter.FROM_REVISION in error
    assert "--reset-database" in error


def test_it_refuses_when_another_table_has_moved(old, capsys):
    with _engine(old).begin() as connection:
        connection.execute(text("ALTER TABLE stories DROP COLUMN emoji"))

    assert converter.main(["--database", str(old)]) == 2

    assert "stories: column 'emoji'" in capsys.readouterr().err
    assert schemacheck.stamped(_engine(old)) == converter.FROM_REVISION, "nothing was written"


def test_it_refuses_a_path_with_no_database(tmp_path, capsys):
    assert converter.main(["--database", str(tmp_path / "missing.db")]) == 2
    assert "no database" in capsys.readouterr().err

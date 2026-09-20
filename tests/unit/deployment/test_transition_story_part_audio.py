"""The one-off converter that added the recording columns to `story_parts`.

**Delete this file together with `scripts/throwaway/add_story_part_audio.py`**, once that has run. It
is tested against a database built the way the owner's was — the current schema minus the new
columns, stamped with the head from before them — because the point of a converter is that words,
pictures and recordings survive it, and a test that started from an empty database would prove
nothing about that.
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
from acervo.db.tables import metadata  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "add_story_part_audio", ROOT / "scripts" / "throwaway" / "add_story_part_audio.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)


def _row(table, **overrides) -> dict:
    """One row of anything, giving every required column a plausible value."""
    row = {}
    for column in table.columns:
        if column.name in overrides:
            row[column.name] = overrides[column.name]
        elif column.nullable:
            continue
        elif "JSON" in str(column.type):
            row[column.name] = "[]"
        elif "INT" in str(column.type).upper() or "BOOL" in str(column.type).upper():
            row[column.name] = 1
        else:
            row[column.name] = "x"
    return row


@pytest.fixture
def old(tmp_path) -> Path:
    """The owner's database as it was: the current schema without the columns, one part in it."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(engine)
    parts = metadata.tables[converter.TABLE]
    row = _row(parts, id="storypart000001", text="Cada martes.", image_ref="stories/a/b-1.webp")
    with engine.begin() as connection:
        for column in converter.COLUMNS:
            connection.execute(text(f"ALTER TABLE {converter.TABLE} DROP COLUMN {column}"))
            row.pop(column, None)
        connection.execute(text(
            f"INSERT INTO {converter.TABLE} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"), row)
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:stamp)"),
                           {"stamp": converter.FROM_REVISION})
    engine.dispose()
    return path


def _query(path: Path, sql: str):
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        with engine.connect() as connection:
            return connection.execute(text(sql)).fetchall()
    finally:
        engine.dispose()


def _stamp(path: Path) -> str | None:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    try:
        return schemacheck.stamped(engine)
    finally:
        engine.dispose()


def test_it_converts_from_the_head_it_was_written_for_and_keeps_every_row(old):
    assert converter.main(["--database", str(old)]) == 0

    assert _stamp(old) == HEAD
    rows = _query(old, f"SELECT id, text, image_ref, audio_ref, audio_voice, audio_segments FROM {converter.TABLE}")
    assert len(rows) == 1
    assert rows[0][:3] == ("storypart000001", "Cada martes.", "stories/a/b-1.webp"), "what was there survives"
    assert rows[0][3:] == ("", "", "[]"), "and every part starts as 'not recorded'"
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []


def test_a_dry_run_checks_everything_and_writes_nothing(old, capsys):
    assert converter.main(["--database", str(old), "--dry-run"]) == 0

    assert _stamp(old) == converter.FROM_REVISION
    held = {row[1] for row in _query(old, f"PRAGMA table_info({converter.TABLE})")}
    assert not held & set(converter.COLUMNS)
    assert "nothing was written" in capsys.readouterr().out


def test_running_it_twice_is_harmless(old, capsys):
    assert converter.main(["--database", str(old)]) == 0
    assert converter.main(["--database", str(old)]) == 0
    assert "Nothing to do" in capsys.readouterr().out


def test_a_run_that_added_the_columns_and_stopped_before_restamping_can_be_finished(old):
    """The stamp and the columns are separate statements; a crash between them must not strand the
    database on a converter that then refuses because the columns are already there."""
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        for name, definition in converter.COLUMNS.items():
            connection.execute(text(f"ALTER TABLE {converter.TABLE} ADD COLUMN {name} {definition}"))
    engine.dispose()
    assert _stamp(old) == converter.FROM_REVISION

    assert converter.main(["--database", str(old)]) == 0

    assert _stamp(old) == HEAD


def test_it_refuses_a_database_stamped_with_any_other_revision_naming_both(old, capsys):
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()

    assert converter.main(["--database", str(old)]) == 2

    error = capsys.readouterr().err
    assert "bootstrap_000000000000" in error and converter.FROM_REVISION in error
    assert "--reset-database" in error


def test_it_refuses_when_anything_but_those_columns_has_moved(old, capsys):
    """The change is only safe because it was purely additive. If another table differs the
    converter is the wrong tool, and it says which."""
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE stories DROP COLUMN emoji"))
    engine.dispose()

    assert converter.main(["--database", str(old)]) == 2

    assert "stories: column 'emoji'" in capsys.readouterr().err
    assert _stamp(old) == converter.FROM_REVISION, "nothing was written"


def test_it_refuses_a_path_with_no_database(tmp_path, capsys):
    assert converter.main(["--database", str(tmp_path / "missing.db")]) == 2
    assert "no database" in capsys.readouterr().err

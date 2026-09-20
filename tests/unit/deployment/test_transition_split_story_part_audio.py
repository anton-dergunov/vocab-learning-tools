"""The one-off converter that split a story part's narration into a file per passage.

**Delete this file together with `scripts/throwaway/split_story_part_audio.py`**, once that has run.
It is tested against a database built the way the owner's was — the current schema plus the two
columns that went, stamped with the head from before them, with a recorded part in it — because the
point of a converter is that the words, the pictures and everything else survive it, and a test that
started from an empty database would prove nothing about that.
"""

from __future__ import annotations

import importlib.util
import json
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
    "split_story_part_audio", ROOT / "scripts" / "throwaway" / "split_story_part_audio.py")
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)

SEGMENTS = json.dumps([
    {"text": "Cada martes. ", "direction": "Calm.", "start": 0, "end": 1.6},
    {"text": "Nadie contestó.", "direction": "Hushed.", "start": 1.72, "end": 2.9},
])


def _row(table, **overrides) -> dict:
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
    """The owner's database as it was: a part with one joined recording and its passage times."""
    path = tmp_path / "acervo.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    metadata.create_all(engine)
    parts = metadata.tables[converter.TABLE]
    row = _row(parts, id="storypart000001", text="Cada martes. Nadie contestó.",
               image_ref="stories/a/b-1f4c8b2e.webp", audio_segments=SEGMENTS,
               audio_provider_id="google-tts", audio_model_id="gemini-2.5-flash-tts",
               audio_voice="Kore")
    with engine.begin() as connection:
        for name, kind in (("audio_ref", "VARCHAR(500)"), ("audio_mime", "VARCHAR(120)")):
            connection.execute(text(
                f"ALTER TABLE {converter.TABLE} ADD COLUMN {name} {kind} NOT NULL DEFAULT ''"))
        row["audio_ref"] = "stories/a/storypart000001-b419a258.ogg"
        row["audio_mime"] = "audio/ogg"
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


def test_it_keeps_the_story_and_returns_only_its_narration_to_not_recorded(old):
    assert converter.main(["--database", str(old)]) == 0

    assert _stamp(old) == HEAD
    rows = _query(old, f"SELECT id, text, image_ref, audio_segments, audio_provider_id, audio_voice "
                       f"FROM {converter.TABLE}")
    assert len(rows) == 1
    assert rows[0][:3] == ("storypart000001", "Cada martes. Nadie contestó.", "stories/a/b-1f4c8b2e.webp"), \
        "the story, its text and its picture are untouched"
    # The passages went with the pair that spoke them: the validator refuses a part that names who
    # read it but has no passages, so half of this would leave a row nothing could write again.
    assert rows[0][3:] == ("[]", "", ""), "and its narration is made again"
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    assert schemacheck.compare(engine, metadata, sorted(metadata.tables)) == []


def test_the_part_s_own_recording_columns_are_gone(old):
    assert converter.main(["--database", str(old)]) == 0

    held = {row[1] for row in _query(old, f"PRAGMA table_info({converter.TABLE})")}
    assert not held & set(converter.DROPPED)
    assert "audio_segments" in held, "a passage still carries its own recording"


def test_a_dry_run_says_how_much_will_be_re_recorded_and_writes_nothing(old, capsys):
    assert converter.main(["--database", str(old), "--dry-run"]) == 0

    printed = capsys.readouterr().out
    assert "1 story parts" in printed and "nothing was written" in printed
    assert _stamp(old) == converter.FROM_REVISION
    held = {row[1] for row in _query(old, f"PRAGMA table_info({converter.TABLE})")}
    assert set(converter.DROPPED) <= held, "the columns are still there"


def test_running_it_twice_is_harmless(old, capsys):
    assert converter.main(["--database", str(old)]) == 0
    assert converter.main(["--database", str(old)]) == 0
    assert "Nothing to do" in capsys.readouterr().out


def test_it_refuses_a_database_stamped_with_any_other_revision_naming_both(old, capsys):
    engine = create_engine(f"sqlite+pysqlite:///{old}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'bootstrap_000000000000'"))
    engine.dispose()

    assert converter.main(["--database", str(old)]) == 2

    error = capsys.readouterr().err
    assert "bootstrap_000000000000" in error and converter.FROM_REVISION in error
    assert "--reset-database" in error


def test_it_refuses_when_another_table_has_moved(old, capsys):
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

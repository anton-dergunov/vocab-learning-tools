"""Creating the schema, and refusing to serve one that is not this one.

This file exists because the guard it tests failed in production. A schema change landed with the
revision id left at its old literal, so `bootstrap` compared a stamped database against an unchanged
head, decided it was current, and served it — whereupon every route that named a new column returned
an anonymous 500 while `/health` and the routes that did not stayed green. The deployment reported
healthy and the interface reported offline, which is the exact confusion the stamp exists to end.

So the thing under test is not really `bootstrap`; it is that **changing the schema changes the
head**, without anybody having to remember.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Index, Integer, MetaData, String, Table, create_engine, text

from acervo.db.bootstrap import SchemaOutOfDate, bootstrap, current_revision, head_revision
from acervo.db.tables import metadata

VERSIONS = Path(__file__).resolve().parents[3] / "src" / "acervo" / "db" / "alembic" / "versions"


def _revision_module():
    """The revision file, loaded the way Alembic loads it — by path, not as a package."""
    spec = importlib.util.spec_from_file_location("acervo_bootstrap_probe", VERSIONS / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _toy(extra: bool = False) -> MetaData:
    described = MetaData()
    columns = [Column("id", String(15), primary_key=True), Column("count", Integer, nullable=False)]
    if extra:
        columns.append(Column("suppressed", Integer, nullable=False))
    Table("things", described, *columns)
    return described


# ── the head follows the schema ─────────────────────────────────────────────


def test_the_head_is_the_same_every_time_it_is_asked():
    """It is compared against what is stamped on disk, so an id that wandered between processes
    would refuse a database the same code had just written."""
    assert head_revision() == head_revision()
    assert head_revision() == _revision_module().revision


def test_a_new_column_changes_the_head_with_nobody_remembering_to():
    shape = _revision_module().shape_of
    assert shape(_toy()) != shape(_toy(extra=True))


def test_a_new_index_changes_it_too():
    """Not only columns: a unique index is the difference between a constraint holding and not."""
    shape = _revision_module().shape_of
    plain = _toy()
    indexed = _toy()
    Index("idx_things_count", indexed.tables["things"].c.count)  # attaches to the table
    assert shape(plain) != shape(indexed)


def test_narrowing_a_partial_index_changes_it_too():
    """`jobs` holds one open `enrich` per word through a partial unique index, and what the index
    covers is its condition — so a condition the digest could not see was a constraint that could
    change with the head standing still."""
    shape = _revision_module().shape_of
    narrow, wide = _toy(), _toy()
    Index("idx_things_count", narrow.tables["things"].c.count, unique=True,
          sqlite_where=text("count > 0"))
    Index("idx_things_count", wide.tables["things"].c.count, unique=True,
          sqlite_where=text("count > 1"))
    assert shape(narrow) != shape(wide)


def test_the_shape_does_not_depend_on_the_order_the_tables_were_built_in():
    """Otherwise the id would move when a table was declared somewhere else in the file, and every
    deployment would demand a rebuild for a change that was not one."""
    shape = _revision_module().shape_of
    forwards, backwards = MetaData(), MetaData()
    for described, order in ((forwards, ("alpha", "beta")), (backwards, ("beta", "alpha"))):
        for name in order:
            Table(name, described, Column("id", String(15), primary_key=True))
    assert shape(forwards) == shape(backwards)


def test_the_real_schema_is_what_the_head_describes():
    """A guard against the digest being computed over something other than what ships."""
    module = _revision_module()
    assert module.revision.endswith(
        hashlib.sha256(module.shape_of(metadata).encode()).hexdigest()[:12]
    )


# ── what bootstrap does with it ─────────────────────────────────────────────


@pytest.fixture
def engine(tmp_path):
    return create_engine(f"sqlite+pysqlite:///{tmp_path / 'acervo.db'}", future=True)


def test_an_empty_database_is_created_and_stamped_at_the_head(engine):
    bootstrap(engine)
    assert current_revision(engine) == head_revision()
    with engine.connect() as connection:
        held = {row[0] for row in connection.execute(
            text("select name from sqlite_master where type='table'")
        )}
    assert {"users", "lexemes", "image_prompts", "image_settings"} <= held


def test_bootstrapping_twice_is_a_no_op(engine):
    bootstrap(engine)
    bootstrap(engine)
    assert current_revision(engine) == head_revision()


def test_a_database_written_under_another_schema_is_refused_by_name(engine):
    """The production failure, as a test. Note what it asserts: not that a route breaks later, but
    that the server refuses to start — the whole point being that a half-working deployment is worse
    than one that fails."""
    bootstrap(engine)
    with engine.begin() as connection:
        connection.execute(text("update alembic_version set version_num = '0002_bootstrap'"))

    with pytest.raises(SchemaOutOfDate) as refused:
        bootstrap(engine)
    assert "0002_bootstrap" in str(refused.value)
    assert head_revision() in str(refused.value)
    # **Both ways out, and the carrying one first.** Naming only `--reset-database` pointed a real
    # deployment at rebuilding a vocabulary whose release shipped a converter for exactly that
    # revision; the owner had to already know `--transition` existed to find it.
    assert "--transition" in str(refused.value)
    assert "--reset-database" in str(refused.value)


def test_a_database_with_tables_but_no_stamp_is_refused_rather_than_stamped(engine):
    """Creating the schema over one that already has tables would be a silent partial migration,
    which is the one thing this repo has no upgrade path for."""
    with engine.begin() as connection:
        connection.execute(text("create table users (id text primary key)"))
    with pytest.raises(SchemaOutOfDate):
        bootstrap(engine)

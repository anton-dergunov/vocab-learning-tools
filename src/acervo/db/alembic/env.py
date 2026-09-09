"""Alembic's entry point.

There is one head and no upgrade path, so this is simpler than the generated template: the caller
hands in an engine through `config.attributes`, and offline mode exists only so `alembic` remains
usable by hand against a URL.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from acervo.db.tables import metadata

target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = context.config.attributes.get("engine")
    if engine is None:
        engine = engine_from_config(
            context.config.get_section(context.config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""The whole Acervo core schema.

The one head. It creates the tables straight from `acervo.db.tables`, rather than restating two
hundred lines of columns and indexes a second time: there is no upgrade path to write a diff
against, so a second description would be a copy with no reader and one more thing to keep in step.

Revision ID: 0001_bootstrap
Revises:
"""

from __future__ import annotations

from alembic import op

from acervo.db.tables import metadata

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())

"""The whole Acervo core schema.

The one head. It creates the tables straight from `acervo.db.tables`, rather than restating two
hundred lines of columns and indexes a second time: there is no upgrade path to write a diff
against, so a second description would be a copy with no reader and one more thing to keep in step.

**The revision id is derived from the schema itself**, and that is the point rather than a flourish.
It used to be the literal `"0002_bootstrap"`, which meant a schema change had to be accompanied by
somebody remembering to bump it — and when that was forgotten the failure was silent and nasty:
`bootstrap` compared a stamped database against an unchanged head, decided it was current, and
served it. Every route that named a new column then failed with an anonymous 500 while `/health` and
the routes that did not stayed green, so the deployment looked healthy and the interface looked
offline. That is the exact failure `bootstrap`'s guard exists to prevent, and an id nobody has to
remember is what makes the guard reliable.

So: change the schema and the head changes with it, whereupon a database written under the old one
is refused by name and `--reset-database` is the documented remedy.

Revises: nothing. There is one head and no upgrade path.
"""

from __future__ import annotations

import hashlib

from alembic import op
from sqlalchemy import MetaData

from acervo.db.tables import metadata


def shape_of(described: MetaData) -> str:
    """A canonical description of every table, column, index and constraint.

    Sorted throughout, so the digest depends on the schema and not on the order Python happened to
    build it in. Deliberately not the compiled DDL: that would tie the id to a dialect, and the
    question this answers — "is the database on disk shaped like this code" — is dialect-free.

    Takes its metadata rather than reaching for the global one, so a test can prove the digest moves
    when a schema changes without mutating the schema that ships.
    """
    lines = []
    for name in sorted(described.tables):
        table = described.tables[name]
        columns = ",".join(
            f"{column.name}:{column.type!r}"
            f":{'null' if column.nullable else 'notnull'}"
            f"{':pk' if column.primary_key else ''}"
            for column in table.columns
        )
        indexes = ",".join(sorted(
            f"{index.name}({','.join(sorted(column.name for column in index.columns))})"
            f"{':unique' if index.unique else ''}"
            for index in table.indexes
        ))
        keys = ",".join(sorted(
            f"{key.parent.name}->{key.target_fullname}:{key.ondelete or ''}"
            for key in table.foreign_keys
        ))
        lines.append(f"{name}[{columns}][{indexes}][{keys}]")
    return "\n".join(lines)


# Underscore, not a hyphen: Alembic refuses `-` in a revision identifier.
revision = f"bootstrap_{hashlib.sha256(shape_of(metadata).encode()).hexdigest()[:12]}"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())

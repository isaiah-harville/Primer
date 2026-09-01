"""Create the vector schema and the extension its columns need.

Revision ID: 0001_vector_schema
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from primer_retrieval.config import Settings

revision: str = "0001_vector_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = Settings().vector_schema


def upgrade() -> None:
    """Make the schema, and the extension that gives it a vector type.

    The chunk table itself is left to the vector integration, which creates
    it on first use. Its columns are that integration's contract rather than
    Primer's, and a hand-copied duplicate here would drift silently the first
    time the integration changed a column and stop matching what it queries.

    `CREATE EXTENSION` needs privileges an application role should not hold.
    Doing it here means the migration runs with them and the service does
    not, which is why the store no longer asks for it at request time.
    """
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Drop the schema and everything the integration put in it.

    Not reversible in any useful sense: the embeddings are gone and must be
    rebuilt from the documents. That is what downgrading this means, and
    pretending otherwise by leaving the schema behind would be worse.

    The extension is left alone. It is database-wide, and another schema may
    be using it.
    """
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")

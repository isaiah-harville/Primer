"""Record which generation answers for each document version.

Revision ID: 0004_document_indexes
Revises: 0003_job_leases
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_document_indexes"
down_revision: str | None = "0003_job_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "control"


def upgrade() -> None:
    op.create_table(
        "document_indexes",
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            [f"{SCHEMA}.document_versions.id"],
            name="fk_document_indexes_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            [f"{SCHEMA}.libraries.id"],
            name="fk_document_indexes_library_id_libraries",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_version_id", name="pk_document_indexes"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_document_indexes_library_id", "document_indexes", ["library_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_document_indexes_library_id", "document_indexes", schema=SCHEMA)
    op.drop_table("document_indexes", schema=SCHEMA)

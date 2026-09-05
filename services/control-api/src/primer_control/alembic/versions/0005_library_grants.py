"""Let a library owner share read access with another user.

Revision ID: 0005_library_grants
Revises: 0004_document_indexes
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_library_grants"
down_revision: str | None = "0004_document_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "control"

#: Uniqueness applies to live grants only. A revoked row is kept as the
#: record of an access that existed, and re-sharing writes a new row beside
#: it - so a plain constraint over the pair would refuse the second share to
#: someone whose access had been taken away and given back.
LIVE_GRANT_INDEX = "uq_library_grants_live"


def upgrade() -> None:
    op.create_table(
        "library_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grantee_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["library_id"],
            [f"{SCHEMA}.libraries.id"],
            name="fk_library_grants_library_id_libraries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grantee_user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_library_grants_grantee_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_library_grants_granted_by_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_library_grants"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_library_grants_library_id",
        "library_grants",
        ["library_id"],
        schema=SCHEMA,
    )
    # The index that answers "what may this person read", which is on the
    # path of every library listing and every question asked of one.
    op.create_index(
        "ix_library_grants_grantee_user_id",
        "library_grants",
        ["grantee_user_id"],
        schema=SCHEMA,
    )
    op.create_index(
        LIVE_GRANT_INDEX,
        "library_grants",
        ["library_id", "grantee_user_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(LIVE_GRANT_INDEX, table_name="library_grants", schema=SCHEMA)
    op.drop_index("ix_library_grants_grantee_user_id", table_name="library_grants", schema=SCHEMA)
    op.drop_index("ix_library_grants_library_id", table_name="library_grants", schema=SCHEMA)
    op.drop_table("library_grants", schema=SCHEMA)

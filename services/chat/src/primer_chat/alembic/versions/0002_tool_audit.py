"""Record every tool call, including the ones that were refused.

Revision ID: 0002_tool_audit
Revises: 0001_conversations
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_tool_audit"
down_revision: str | None = "0001_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"
PHASES = ("requested", "approved", "denied", "running", "completed", "failed", "expired")


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(length=200), nullable=False),
        sa.Column("server_name", sa.String(length=64), nullable=False),
        sa.Column(
            "arguments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("output", sa.String(length=8000), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "phase IN (" + ", ".join(f"'{phase}'" for phase in PHASES) + ")",
            name="phase_known",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            [f"{SCHEMA}.conversations.id"],
            name="fk_tool_calls_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_calls"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_tool_calls_conversation_id", "tool_calls", ["conversation_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_tool_calls_conversation_id", "tool_calls", schema=SCHEMA)
    op.drop_table("tool_calls", schema=SCHEMA)

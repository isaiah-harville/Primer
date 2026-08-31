"""Create the Chat schema with conversations, messages, and citations.

Revision ID: 0001_conversations
Revises:
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_conversations"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"
ROLES = ("user", "assistant")
STATES = ("streaming", "completed", "failed", "cancelled")


def _values(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        schema=SCHEMA,
    )
    op.create_index("ix_conversations_library_id", "conversations", ["library_id"], schema=SCHEMA)
    op.create_index(
        "ix_conversations_owner_user_id", "conversations", ["owner_user_id"], schema=SCHEMA
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("provider_model", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"role IN ({_values(ROLES)})", name="role_known"),
        sa.CheckConstraint(f"state IN ({_values(STATES)})", name="state_known"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            [f"{SCHEMA}.conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        schema=SCHEMA,
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], schema=SCHEMA)

    op.create_table(
        "message_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("excerpt", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(
            ["message_id"],
            [f"{SCHEMA}.messages.id"],
            name="fk_message_citations_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_citations"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_message_citations_message_id", "message_citations", ["message_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_message_citations_message_id", "message_citations", schema=SCHEMA)
    op.drop_table("message_citations", schema=SCHEMA)
    op.drop_index("ix_messages_conversation_id", "messages", schema=SCHEMA)
    op.drop_table("messages", schema=SCHEMA)
    op.drop_index("ix_conversations_owner_user_id", "conversations", schema=SCHEMA)
    op.drop_index("ix_conversations_library_id", "conversations", schema=SCHEMA)
    op.drop_table("conversations", schema=SCHEMA)

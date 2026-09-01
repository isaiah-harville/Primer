"""Give a conversation's messages a definite order.

Revision ID: 0004_message_ordinal
Revises: 0003_optional_library
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_message_ordinal"
down_revision: str | None = "0003_optional_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """Order messages by a counter rather than by their timestamp.

    `created_at` defaults to `now()`, which in PostgreSQL is the start of the
    transaction. A turn writes the question and the answer in one
    transaction, so the two carry the same instant and sorting by it falls
    back to comparing random UUIDs - which puts the answer before the
    question about half the time. That was tolerable while the transcript was
    only read back for display; it is not, now that it is replayed to a model
    as the conversation so far.
    """
    op.add_column(
        "messages",
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    # Existing rows get the order they would have been read in. Where the
    # timestamps tie the choice is arbitrary, but it is made once here and
    # then fixed, rather than being redrawn on every read.
    op.execute(
        sa.text("""
        UPDATE chat.messages AS m
        SET ordinal = numbered.position
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY conversation_id ORDER BY created_at, id
            ) - 1 AS position
            FROM chat.messages
        ) AS numbered
        WHERE m.id = numbered.id
        """)
    )
    # The conversation and the order it is read in, together. The plain
    # index on the conversation is dropped rather than kept beside it: this
    # one begins with the same column, so it answers everything that one did.
    op.create_index(
        "ix_messages_conversation_id_ordinal",
        "messages",
        ["conversation_id", "ordinal"],
        schema=SCHEMA,
    )
    op.drop_index("ix_messages_conversation_id", "messages", schema=SCHEMA)


def downgrade() -> None:
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], schema=SCHEMA)
    op.drop_index("ix_messages_conversation_id_ordinal", "messages", schema=SCHEMA)
    op.drop_column("messages", "ordinal", schema=SCHEMA)

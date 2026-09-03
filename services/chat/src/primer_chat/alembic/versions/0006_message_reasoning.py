"""Keep what a reasoning model worked through, beside what it answered.

Revision ID: 0006_message_reasoning
Revises: 0005_conversation_summary
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_message_reasoning"
down_revision: str | None = "0005_conversation_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """Give a message somewhere to keep the thinking behind it.

    Nullable with no default and nothing backfilled, because the three states
    are genuinely different: null is a model that does not reason aloud,
    empty is one that does and said nothing this turn, and text is what it
    thought. A default of empty string would tell every answer written before
    this migration that it came from a reasoning model with nothing to say.

    A column rather than its own table: there is exactly one per message, it
    is read whenever the message is, and a join to fetch a string that is
    already one-to-one buys nothing.
    """
    op.add_column(
        "messages",
        sa.Column("reasoning", sa.Text(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("messages", "reasoning", schema=SCHEMA)

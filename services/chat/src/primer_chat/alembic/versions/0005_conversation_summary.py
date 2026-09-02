"""Remember the turns that fall out of the context window.

Revision ID: 0005_conversation_summary
Revises: 0004_message_ordinal
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_conversation_summary"
down_revision: str | None = "0004_message_ordinal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """Give a conversation somewhere to keep what it no longer replays.

    Both nullable, and nothing is backfilled: an existing conversation has
    compacted nothing, which is what null says. The first turn that overflows
    the window writes them.
    """
    op.add_column(
        "conversations",
        sa.Column("summary", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "conversations",
        sa.Column("summary_through_ordinal", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Forget the summaries. The messages they stood in for are still there."""
    op.drop_column("conversations", "summary_through_ordinal", schema=SCHEMA)
    op.drop_column("conversations", "summary", schema=SCHEMA)

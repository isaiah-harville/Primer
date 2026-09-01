"""Let a conversation have no library.

Revision ID: 0003_optional_library
Revises: 0002_tool_audit
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_optional_library"
down_revision: str | None = "0002_tool_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """A conversation with no library is answered without retrieval."""
    op.alter_column(
        "conversations",
        "library_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Refuse rather than guess.

    Ungrounded conversations have no library to restore, and inventing one
    would attach a stranger's thread to a real library. If any exist, the
    operator has to decide what becomes of them.
    """
    connection = op.get_bind()
    # A literal, not a formatted string: the schema is a constant here, and
    # writing it out means there is nothing to reason about.
    ungrounded = connection.execute(
        sa.text("SELECT count(*) FROM chat.conversations WHERE library_id IS NULL")
    ).scalar_one()
    if ungrounded:
        message = (
            f"{ungrounded} conversation(s) have no library. Delete or reassign them "
            "before downgrading; this migration will not choose a library for them."
        )
        raise RuntimeError(message)

    op.alter_column(
        "conversations",
        "library_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema=SCHEMA,
    )

"""Let a deployment hold more than one inference endpoint.

Revision ID: 0007_providers
Revises: 0006_message_reasoning
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_providers"
down_revision: str | None = "0006_message_reasoning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """Somewhere to keep the endpoints added through the settings page.

    Only those. The one configured in the chart stays in the environment and
    is reported alongside these, so a deployment that never opens the
    settings page has an empty table and behaves exactly as it did before.

    The name is unique because it is how a person tells two endpoints apart,
    and two called "Local" would make the choice in front of a user
    meaningless. The key column holds ciphertext or nothing at all.
    """
    op.create_table(
        "providers",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("base_url", sa.String(2000), nullable=False),
        sa.Column("api_key_sealed", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("providers", schema=SCHEMA)

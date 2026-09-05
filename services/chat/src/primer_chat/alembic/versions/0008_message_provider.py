"""Record which provider served the model that answered.

Revision ID: 0008_message_provider
Revises: 0007_providers
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_message_provider"
down_revision: str | None = "0007_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "chat"


def upgrade() -> None:
    """Give a message somewhere to record where its answer came from.

    `provider_model` already said which model wrote an answer, but a model
    name does not identify an endpoint: two providers serving `llama3.1:8b`
    is the ordinary case. Reopening a conversation could therefore say what
    it had been answered by without being able to select it again, and a
    follow-up went to the deployment's default instead - silently changing
    models in the middle of a thread.

    Nullable with nothing backfilled. Null means genuinely unknown: an
    answer written before this column existed, or one served by the endpoint
    configured for the deployment rather than by a provider row. Inventing a
    provider for those would attribute answers to an endpoint that may never
    have produced them.

    Deliberately not a foreign key. An administrator removing a provider
    must not take the record of what answered a question down with it, or
    cascade a conversation's history away; this is a note about the past,
    not a pointer to something that has to still exist.
    """
    op.add_column(
        "messages",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("messages", "provider_id", schema=SCHEMA)

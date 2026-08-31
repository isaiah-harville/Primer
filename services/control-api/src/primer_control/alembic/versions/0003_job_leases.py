"""Lease ingestion jobs and add the terminal deleted state.

Revision ID: 0003_job_leases
Revises: 0002_documents
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_leases"
down_revision: str | None = "0002_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "control"

PREVIOUS_STATES = (
    "queued",
    "parsing",
    "chunking",
    "embedding",
    "indexing",
    "ready",
    "failed",
    "unsupported",
    "cancelled",
    "deleting",
)
STATES = (*PREVIOUS_STATES, "deleted")


def _condition(states: Sequence[str]) -> str:
    return "state IN (" + ", ".join(f"'{state}'" for state in states) + ")"


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Short name on both sides: the metadata naming convention expands it to
    # ck_ingestion_jobs_state_known, and spelling the full name applies the
    # template twice.
    op.drop_constraint("state_known", "ingestion_jobs", type_="check", schema=SCHEMA)
    op.create_check_constraint("state_known", "ingestion_jobs", _condition(STATES), schema=SCHEMA)


def downgrade() -> None:
    # Short name on both sides: the metadata naming convention expands it to
    # ck_ingestion_jobs_state_known, and spelling the full name applies the
    # template twice.
    op.drop_constraint("state_known", "ingestion_jobs", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        "state_known", "ingestion_jobs", _condition(PREVIOUS_STATES), schema=SCHEMA
    )
    op.drop_column("ingestion_jobs", "lease_expires_at", schema=SCHEMA)
    op.drop_column("ingestion_jobs", "claimed_at", schema=SCHEMA)

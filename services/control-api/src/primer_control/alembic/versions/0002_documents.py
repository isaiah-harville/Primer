"""Add documents, immutable versions, deduplicated sources, and ingestion jobs.

Revision ID: 0002_documents
Revises: 0001_users_libraries
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_documents"
down_revision: str | None = "0001_users_libraries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "control"

STATES = (
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


def upgrade() -> None:
    op.create_table(
        "source_objects",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("sha256", name="pk_source_objects"),
        schema=SCHEMA,
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("library_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["library_id"],
            [f"{SCHEMA}.libraries.id"],
            name="fk_documents_library_id_libraries",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        schema=SCHEMA,
    )
    op.create_index("ix_documents_library_id", "documents", ["library_id"], schema=SCHEMA)

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [f"{SCHEMA}.documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_sha256"],
            [f"{SCHEMA}.source_objects.sha256"],
            name="fk_document_versions_source_sha256_source_objects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_id"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_document_versions_document_id", "document_versions", ["document_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_document_versions_source_sha256", "document_versions", ["source_sha256"], schema=SCHEMA
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{state}'" for state in STATES) + ")",
            # The metadata naming convention expands this to
            # ck_ingestion_jobs_state_known; spelling the full name here
            # would apply the template twice.
            name="state_known",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            [f"{SCHEMA}.document_versions.id"],
            name="fk_ingestion_jobs_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ingestion_jobs_document_version_id",
        "ingestion_jobs",
        ["document_version_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_document_version_id", "ingestion_jobs", schema=SCHEMA)
    op.drop_table("ingestion_jobs", schema=SCHEMA)
    op.drop_index("ix_document_versions_source_sha256", "document_versions", schema=SCHEMA)
    op.drop_index("ix_document_versions_document_id", "document_versions", schema=SCHEMA)
    op.drop_table("document_versions", schema=SCHEMA)
    op.drop_index("ix_documents_library_id", "documents", schema=SCHEMA)
    op.drop_table("documents", schema=SCHEMA)
    op.drop_table("source_objects", schema=SCHEMA)

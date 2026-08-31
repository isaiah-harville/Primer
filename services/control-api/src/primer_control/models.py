"""Control-owned SQLAlchemy models.

Control keeps its tables in a dedicated schema so Chat can own its own
migration history against the same PostgreSQL instance without either
service's Alembic run touching the other's tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from primer_contracts.documents import IngestionStatus
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONTROL_SCHEMA = "control"

#: Explicit names keep Alembic autogenerate deterministic, so a constraint can
#: be dropped by name in a later migration on any database.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=CONTROL_SCHEMA, naming_convention=NAMING_CONVENTION)


class User(Base):
    """A Primer identity, keyed by the stable OIDC subject."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Library(Base):
    """A private collection of source material.

    `owner_user_id` records who created the library. It is not consulted
    directly by routes: authorization goes through LibraryAccess, so adding a
    membership table later does not require changing every caller.
    """

    __tablename__ = "libraries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    #: Soft deletion: a tombstoned library stops being retrievable immediately
    #: while its documents and vectors are cleaned up asynchronously.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceObject(Base):
    """One immutable blob of uploaded bytes, addressed by content.

    Two users uploading identical bytes share this row and the single stored
    object behind it. Nothing here identifies who uploaded it: ownership is a
    property of the document versions that reference it, so deduplication can
    never leak one library's contents into another's authorization decision.
    """

    __tablename__ = "source_objects"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Document(Base):
    """A file in a library, tracked across replacements.

    The document is the stable identity a user cites and links to; its bytes
    live in versions. There is deliberately no `current_version_id` column:
    a pointer alongside the version rows is a second source of truth that can
    disagree with them, and it would need a circular foreign key. The current
    version is the highest `version_number`, which cannot drift.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    library_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.libraries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    #: Tombstone first, clean up vectors and unreferenced sources afterwards.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    """Immutable bytes plus the filename they arrived under.

    Versions are never updated. A replacement adds a row, so a citation
    pinned to a version keeps resolving to exactly the text that was quoted
    even after the document is replaced.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: RESTRICT, not CASCADE: a source object may back versions in several
    #: libraries, so it is only removable once nothing references it.
    source_sha256: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{CONTROL_SCHEMA}.source_objects.sha256", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


#: Persisted job states. These are the wire `IngestionStatus` values, so a
#: user-visible status never needs translating between two vocabularies that
#: could fall out of step.
JOB_STATES = tuple(status.value for status in IngestionStatus)


class IngestionJob(Base):
    """The progress of turning one version into retrievable chunks.

    `generation_id` labels the index build this job feeds. A retry or a
    configuration change starts a new generation, so a redelivered message
    for a superseded generation can be recognized and dropped rather than
    writing chunks into the index users are currently searching.
    """

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN (" + ", ".join(f"'{state}'" for state in JOB_STATES) + ")",
            name="state_known",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: A lease, not a boolean flag: a worker that dies mid-stage stops
    #: renewing, and the stage becomes claimable again on its own rather than
    #: staying stuck until an operator intervenes.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Sanitized for display. Exception traces belong in logs, correlated by
    #: request ID, not in a field a user can read.
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentIndex(Base):
    """Which generation currently answers for a document version.

    One row per version, not per generation: this is a pointer, and the
    generations themselves are recorded on the jobs that built them. Moving
    the pointer is what "activation" means, and it is a single row update so
    a rebuild becomes visible all at once rather than document by document.
    """

    __tablename__ = "document_indexes"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.document_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    library_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CONTROL_SCHEMA}.libraries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The generation retrieval should search. Null while the first index is
    #: still being built, which is how a document with no answers yet is
    #: distinguished from one whose answers are empty.
    active_generation_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

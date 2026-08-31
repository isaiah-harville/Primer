"""Chat-owned SQLAlchemy models.

Chat keeps its tables in their own schema. It shares a PostgreSQL instance
with Control but not a migration history, so neither service's Alembic run
touches the other's tables and the two can be released separately.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from primer_contracts.chat import MessageRole, MessageState
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CHAT_SCHEMA = "chat"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ROLES = tuple(role.value for role in MessageRole)
STATES = tuple(state.value for state in MessageState)


class Base(DeclarativeBase):
    metadata = MetaData(schema=CHAT_SCHEMA, naming_convention=NAMING_CONVENTION)


class Conversation(Base):
    """A thread of questions about one library.

    `owner_user_id` and `library_id` are stored rather than looked up,
    because every request re-authorizes against Control anyway: these are
    what the request is checked against, not what it is trusted on.

    There is no foreign key to Control's tables. Chat has its own schema and
    no business enforcing another service's referential integrity; a deleted
    library stops answering because Control says so, not because a cascade
    reached in here.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    library_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Message(Base):
    """One turn. Content is immutable once the turn reaches a terminal state.

    A message left in `streaming` is a stream that died rather than an
    answer that failed, and the two are kept distinguishable: one is a
    recoverable fault, the other is something the user needs to be told.
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN (" + ", ".join(f"'{role}'" for role in ROLES) + ")", name="role_known"
        ),
        CheckConstraint(
            "state IN (" + ", ".join(f"'{state}'" for state in STATES) + ")", name="state_known"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CHAT_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    #: Which endpoint and model produced this, recorded per message: a
    #: deployment can change models between turns, and an answer's provenance
    #: is part of the answer.
    provider_model: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MessageCitation(Base):
    """What an answer was grounded in, recorded with the answer.

    Stored rather than recomputed: what a reply cited is a fact about that
    reply, and re-retrieving later would produce today's passages for
    yesterday's words.

    The excerpt is kept too. A citation whose document is later deleted still
    shows what was quoted, which is what makes an old answer auditable rather
    than merely a dead link.
    """

    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{CHAT_SCHEMA}.messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(255))
    excerpt: Mapped[str | None] = mapped_column(String(2000))

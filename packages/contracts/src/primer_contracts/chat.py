"""Chat, citation, and streaming contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from primer_contracts.base import WireModel
from primer_contracts.identity import Principal
from primer_contracts.retrieval import SourceLocator

Message = Annotated[str, Field(min_length=1, max_length=32000)]


class Citation(WireModel):
    """A grounded reference from an assistant response to a source passage.

    Citations address an immutable document version so a later replacement
    cannot silently change what an existing answer claimed to cite.
    """

    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    locator: SourceLocator | None = None
    excerpt: str | None = Field(default=None, max_length=2000)


class ChatRequest(WireModel):
    """A user turn scoped to one of the principal's libraries."""

    principal: Principal
    library_id: UUID
    message: Message
    conversation_id: UUID | None = None
    tools_enabled: bool = False


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageState(StrEnum):
    """A message is always in exactly one of these.

    `STREAMING` is the only non-terminal state. A message left in it is a
    stream that died, which is a recoverable fault rather than an answer, and
    is distinguishable from one that genuinely failed.
    """

    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConversationSummary(WireModel):
    """A conversation, which belongs to one library and one person."""

    id: UUID
    library_id: UUID
    owner_user_id: UUID
    title: str = Field(max_length=200)
    created_at: datetime
    updated_at: datetime


class MessageSummary(WireModel):
    """One turn, and what it was grounded in.

    Citations are stored with the message rather than recomputed, because
    what an answer cited is a fact about that answer. Re-retrieving later
    would produce today's passages for yesterday's words.

    Content keeps its whitespace, like `MessageDelta`, so that concatenating
    a stream's fragments yields exactly the stored answer. Trimming here
    would make the two disagree for any answer that begins or ends with
    space, and a client comparing them would be right to think it had lost
    something.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    state: MessageState
    content: str
    citations: tuple[Citation, ...] = ()
    error_code: str | None = Field(default=None, max_length=64)
    created_at: datetime


class StreamEvent(WireModel):
    """Base for everything sent over SSE.

    Every event carries a monotonic id within its stream, so a client that
    reconnects can say what it already saw, and one that receives events out
    of order can tell.
    """

    id: int = Field(ge=0)


class MessageStarted(StreamEvent):
    type: Literal["message.started"] = "message.started"
    message_id: UUID
    conversation_id: UUID


class MessageDelta(StreamEvent):
    """A fragment of the answer, exactly as the model produced it.

    Whitespace is deliberately not stripped here, unlike every other wire
    string. Fragments are concatenated by the client, and the space between
    two words routinely arrives as the leading or trailing character of a
    fragment - stripping it silently welds words together in the reader's
    copy while the stored answer looks fine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    type: Literal["message.delta"] = "message.delta"
    text: str


class CitationEvent(StreamEvent):
    """A source the answer is grounded in.

    Sent as the context is assembled, before any text, so a reader can see
    what the answer is being drawn from while it is still being written.
    """

    type: Literal["citation"] = "citation"
    index: int = Field(ge=1)
    citation: Citation


class MessageCompleted(StreamEvent):
    type: Literal["message.completed"] = "message.completed"
    message: MessageSummary


class StreamError(StreamEvent):
    """A terminal failure, carrying a stable code and nothing else.

    Never a stack trace and never the prompt: a stream is the one place
    where an unfiltered exception would be shown directly to a user.
    """

    type: Literal["error"] = "error"
    code: str = Field(min_length=1, max_length=64)
    detail: str | None = Field(default=None, max_length=2000)


class Heartbeat(StreamEvent):
    """Keeps an idle connection open through proxies that time it out."""

    type: Literal["heartbeat"] = "heartbeat"

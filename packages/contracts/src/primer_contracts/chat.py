"""Chat and citation contracts."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field

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

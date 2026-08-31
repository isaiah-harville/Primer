"""Retrieval contracts.

Every request carries both the acting principal and an explicit library
scope. The Retrieval service rejects unscoped queries, so the scope is
required here rather than inferred from ownership.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel
from primer_contracts.identity import Principal

Query = Annotated[str, Field(min_length=1, max_length=4000)]


class SourceLocator(WireModel):
    """Where a passage sits inside its source document.

    Locators are user-meaningful positions only. Filesystem or object-store
    paths are deliberately absent from citation-facing contracts.
    """

    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=255)


class RetrievalRequest(WireModel):
    """A user- and library-scoped search."""

    principal: Principal
    library_id: UUID
    query: Query
    limit: int = Field(default=8, ge=1, le=50)


class RetrievedChunk(WireModel):
    """A ranked passage with the scope needed to authorize and cite it."""

    chunk_id: UUID
    library_id: UUID
    document_id: UUID
    document_version_id: UUID
    content: str
    score: float
    locator: SourceLocator | None = None
    index_generation: int | None = Field(default=None, ge=1)

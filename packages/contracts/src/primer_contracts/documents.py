"""Document and ingestion-status contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel


class IngestionStatus(StrEnum):
    """Deterministic states a user can observe for a document version."""

    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    DELETING = "deleting"


class DocumentSummary(WireModel):
    """A document and the state of its current immutable version."""

    id: UUID
    library_id: UUID
    current_version_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(ge=0)
    status: IngestionStatus
    status_detail: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    updated_at: datetime

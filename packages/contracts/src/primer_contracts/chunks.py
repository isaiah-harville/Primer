"""The unit of retrievable content, passed from ingestion to retrieval.

Chunks cross a service boundary as Primer contracts rather than as Haystack
documents. Retrieval owns the document store exclusively, so the shape
Haystack wants is its business alone; putting a Haystack type on the wire
would spread that ownership across two services and make an upgrade there a
coordinated release here.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel
from primer_contracts.retrieval import SourceLocator


class DocumentChunk(WireModel):
    """One passage, with everything needed to authorize and cite it.

    Scope is carried on every chunk, not attached at index time. A chunk that
    could not name its library could not be filtered by one, and retrieval's
    isolation guarantee is exactly that filter.
    """

    chunk_id: UUID
    #: Position within the version, so a citation can be resolved back to a
    #: place in the document even if chunking parameters later change.
    ordinal: int = Field(ge=0)

    library_id: UUID
    document_id: UUID
    document_version_id: UUID
    owner_user_id: UUID
    #: Which index build this chunk belongs to. Retrieval filters on the
    #: active generation, so a half-written rebuild is never searchable.
    generation_id: UUID

    #: Exactly what the document says, and what a citation quotes. Never
    #: augmented: an excerpt a reader cannot find in the source is a
    #: fabrication, however useful it was for matching.
    content: str = Field(min_length=1)
    #: What gets embedded. Headings are prepended here because a passage read
    #: without its section title often loses the subject it is about.
    embedding_text: str = Field(min_length=1)

    locator: SourceLocator = SourceLocator()
    filename: str = Field(min_length=1, max_length=255)

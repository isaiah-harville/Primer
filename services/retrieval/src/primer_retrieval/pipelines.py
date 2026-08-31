"""Embedding, filtering, and the translation at Primer's boundary.

Haystack types live behind this module. Chunks arrive and leave as Primer
contracts, so a Haystack upgrade is a change here rather than a coordinated
release across ingestion and chat.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from haystack import Document
from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.document_stores.types import DocumentStore
from haystack.utils import Secret
from haystack_integrations.components.retrievers.pgvector import PgvectorEmbeddingRetriever
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever
from primer_contracts.chunks import DocumentChunk
from primer_contracts.retrieval import RetrievedChunk, SourceLocator

from primer_retrieval.config import Settings

#: Meta keys Primer filters and cites on. Named once because a typo in one
#: of them is an isolation failure, not a formatting bug.
LIBRARY_ID = "library_id"
GENERATION_ID = "generation_id"
DOCUMENT_ID = "document_id"
VERSION_ID = "document_version_id"
OWNER_ID = "owner_user_id"


class TextEmbedder(Protocol):
    def run(self, text: str) -> dict[str, Any]: ...


class DocumentEmbedder(Protocol):
    def run(self, documents: list[Document]) -> dict[str, Any]: ...


def build_text_embedder(settings: Settings) -> TextEmbedder:
    return OpenAITextEmbedder(
        api_key=Secret.from_token(
            settings.embedding_api_key.get_secret_value() if settings.embedding_api_key else "none"
        ),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_base_url=settings.embedding_base_url,
        timeout=settings.embedding_timeout_seconds,
    )


def build_document_embedder(settings: Settings) -> DocumentEmbedder:
    return OpenAIDocumentEmbedder(
        api_key=Secret.from_token(
            settings.embedding_api_key.get_secret_value() if settings.embedding_api_key else "none"
        ),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_base_url=settings.embedding_base_url,
        timeout=settings.embedding_timeout_seconds,
        progress_bar=False,
    )


def build_retriever(store: DocumentStore, settings: Settings) -> Any:
    if settings.vector_store == "qdrant":
        return QdrantEmbeddingRetriever(document_store=store)  # ty: ignore[invalid-argument-type]
    return PgvectorEmbeddingRetriever(document_store=store)  # ty: ignore[invalid-argument-type]


def scope_filter(library_id: UUID, generation_ids: tuple[UUID, ...]) -> dict[str, Any]:
    """The filter every read and every delete carries.

    Built in one place and never assembled at a call site. Isolation that
    depends on each caller remembering to add a condition is isolation that
    holds until the first caller forgets.
    """
    return {
        "operator": "AND",
        "conditions": [
            {"field": f"meta.{LIBRARY_ID}", "operator": "==", "value": str(library_id)},
            {
                "field": f"meta.{GENERATION_ID}",
                "operator": "in",
                "value": [str(generation) for generation in generation_ids],
            },
        ],
    }


def to_documents(chunks: tuple[DocumentChunk, ...], embedder: DocumentEmbedder) -> list[Document]:
    """Embed chunks, then store what the document actually says.

    Two texts, deliberately. The vector is built from `embedding_text`, which
    carries section headings so a passage keeps the subject it is about. What
    is stored and later quoted is `content`, verbatim. Storing the augmented
    text would put words in a citation that are not in the document.
    """
    embedded = embedder.run([_for_embedding(chunk) for chunk in chunks])
    vectors = {document.id: document.embedding for document in embedded["documents"]}
    return [_for_storage(chunk, vectors[str(chunk.chunk_id)]) for chunk in chunks]


def _for_embedding(chunk: DocumentChunk) -> Document:
    return Document(id=str(chunk.chunk_id), content=chunk.embedding_text)


def _for_storage(chunk: DocumentChunk, embedding: list[float] | None) -> Document:
    return Document(
        id=str(chunk.chunk_id),
        content=chunk.content,
        embedding=embedding,
        meta={
            LIBRARY_ID: str(chunk.library_id),
            GENERATION_ID: str(chunk.generation_id),
            DOCUMENT_ID: str(chunk.document_id),
            VERSION_ID: str(chunk.document_version_id),
            OWNER_ID: str(chunk.owner_user_id),
            "ordinal": chunk.ordinal,
            "filename": chunk.filename,
            "page": chunk.locator.page,
            "section": chunk.locator.section,
        },
    )


def to_retrieved(document: Document) -> RetrievedChunk:
    """Translate a store hit back into Primer's contract."""
    meta = document.meta
    return RetrievedChunk(
        chunk_id=UUID(str(document.id)),
        library_id=UUID(str(meta[LIBRARY_ID])),
        document_id=UUID(str(meta[DOCUMENT_ID])),
        document_version_id=UUID(str(meta[VERSION_ID])),
        content=document.content or "",
        score=float(document.score or 0.0),
        locator=SourceLocator(page=meta.get("page"), section=meta.get("section")),
        index_generation=UUID(str(meta[GENERATION_ID])),
    )

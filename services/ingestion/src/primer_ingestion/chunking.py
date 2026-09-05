"""Turning a converted document into scoped, citable chunks.

Chunking is Docling's `HybridChunker`, configured from deployment settings.
Primer adds no chunking algorithm of its own: splitting text well is a
solved problem, and a bespoke splitter here would be a second thing to
maintain that produced worse citations.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from docling.chunking import HierarchicalChunker, HybridChunker
from docling_core.transforms.chunker import BaseChunk, BaseChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DoclingDocument
from primer_contracts.chunks import DocumentChunk
from primer_contracts.retrieval import SourceLocator

from primer_ingestion.config import Settings
from primer_ingestion.errors import PermanentStageError, UnsupportedDocument

logger = logging.getLogger(__name__)

#: A stable namespace so a chunk's id is a function of its version,
#: generation, and position. Re-running a stage produces the same ids, which
#: is what lets an interrupted index build be finished rather than doubled.
CHUNK_NAMESPACE = uuid.UUID("9c8f1c62-8e0e-5f1c-9d3a-2b4c6e8a0d11")


@dataclass(frozen=True)
class DocumentContext:
    """Who and what a chunk belongs to.

    Every field here ends up on every chunk. They are carried rather than
    looked up later because retrieval authorizes by filtering on them, and a
    filter cannot consult a database.
    """

    owner_user_id: UUID
    library_id: UUID
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    filename: str


def build_chunker(settings: Settings) -> BaseChunker:
    """Choose a chunker from configuration.

    `HybridChunker` bounds chunks by the embedding model's token budget and
    merges the small pieces that structure alone leaves behind, both of
    which need that model's tokenizer.

    Without one, chunking falls back to document structure. That fallback
    exists for the cases that genuinely have no tokenizer to load - tests
    that must not reach the network, a first run offline - and it is not a
    milder version of the same thing. Structure alone emits one chunk per
    text item and never merges adjacent ones, so a document whose layout is
    many short items - a form, a statement, most scanned PDFs - is stored as
    one chunk per line. Measured on a W2-shaped document: 20 chunks
    averaging 13 characters, against a single 274-character passage with
    peers merged.

    It is warned about rather than chosen silently, because the symptom
    (citations that quote a couple of words) points nowhere near the cause.
    """
    if not settings.chunk_tokenizer:
        logger.warning(
            "No chunk tokenizer configured; splitting on document structure alone. "
            "Adjacent short passages will not be merged, so forms, statements and "
            "scanned documents are stored a line at a time and citations quote "
            "fragments. Set PRIMER_CHUNK_TOKENIZER to the embedding model's tokenizer."
        )
        return HierarchicalChunker()
    try:
        tokenizer = HuggingFaceTokenizer.from_pretrained(
            settings.chunk_tokenizer, max_tokens=settings.max_chunk_tokens
        )
    except Exception as error:
        # Raised while the worker is starting, before it claims a job, so
        # this is a crash loop with a legible reason rather than documents
        # failing one at a time. Falling back here would be worse: it would
        # answer a misconfiguration by quietly doing the thing the operator
        # configured this setting to avoid.
        raise RuntimeError(
            f"The chunk tokenizer {settings.chunk_tokenizer!r} could not be loaded. "
            "It must name a Hugging Face repository this worker can reach - normally "
            "the embedding model's own id, such as 'Qwen/Qwen3-Embedding-0.6B'. A "
            "hosted embedding model that publishes no tokenizer has none to name."
        ) from error
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def locator_for(chunk: BaseChunk) -> SourceLocator:
    """Where in the source this passage came from.

    Page numbers exist only for formats that have pages; Markdown and text
    have headings instead. A locator with neither is honest about not
    knowing rather than inventing a position.
    """
    page: int | None = None
    for item in getattr(chunk.meta, "doc_items", []) or []:
        for provenance in getattr(item, "prov", []) or []:
            page_no = getattr(provenance, "page_no", None)
            if page_no is not None:
                page = int(page_no) if page is None else min(page, int(page_no))
    headings = getattr(chunk.meta, "headings", None) or []
    section = " > ".join(str(heading) for heading in headings) or None
    return SourceLocator(page=page, section=section)


def chunk_id_for(context: DocumentContext, ordinal: int) -> UUID:
    return uuid.uuid5(
        CHUNK_NAMESPACE,
        f"{context.document_version_id}:{context.generation_id}:{ordinal}",
    )


@dataclass(frozen=True)
class Passage:
    """One piece of retrievable text, before it is given an identity."""

    content: str
    embedding_text: str
    locator: SourceLocator


def _from_chunker(document: DoclingDocument, chunker: BaseChunker) -> Iterator[Passage]:
    for chunk in chunker.chunk(document):
        text = (chunk.text or "").strip()
        if not text:
            continue
        yield Passage(
            content=text,
            embedding_text=chunker.contextualize(chunk).strip() or text,
            locator=locator_for(chunk),
        )


def _from_text_items(document: DoclingDocument) -> Iterator[Passage]:
    """Fall back to the document's own text items.

    Chunkers treat a heading as context for the passage beneath it, so a
    document that is *only* headings chunks to nothing: a title slide, a
    one-line scan, an outline. Its text is plainly there, and reporting "no
    text found" for it would be wrong, so the text items are used directly.
    """
    for item in getattr(document, "texts", []) or []:
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue
        page: int | None = None
        for provenance in getattr(item, "prov", []) or []:
            page_no = getattr(provenance, "page_no", None)
            if page_no is not None:
                page = int(page_no) if page is None else min(page, int(page_no))
        yield Passage(content=text, embedding_text=text, locator=SourceLocator(page=page))


def to_chunks(
    document: DoclingDocument,
    chunker: BaseChunker,
    context: DocumentContext,
    *,
    max_chunks: int,
    ocr_attempted: bool = True,
) -> list[DocumentChunk]:
    """Convert a converted document into Primer's wire chunks.

    Exceeding the chunk ceiling fails the job rather than truncating it. A
    silently shortened document would answer questions from half its content
    and give no sign that the other half was dropped.
    """
    passages = list(_from_chunker(document, chunker)) or list(_from_text_items(document))

    chunks: list[DocumentChunk] = []
    for ordinal, passage in enumerate(passages):
        if ordinal >= max_chunks:
            raise PermanentStageError(
                "too_many_chunks",
                f"The document produced more than {max_chunks} chunks.",
            )
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id_for(context, ordinal),
                ordinal=ordinal,
                library_id=context.library_id,
                document_id=context.document_id,
                document_version_id=context.document_version_id,
                owner_user_id=context.owner_user_id,
                generation_id=context.generation_id,
                content=passage.content,
                embedding_text=passage.embedding_text,
                locator=passage.locator,
                filename=context.filename,
            )
        )

    if not chunks:
        # The two cases need different codes because they need different
        # answers from the user: enable OCR, or supply a document that has
        # text in it at all.
        if ocr_attempted:
            raise UnsupportedDocument(
                "no_text_found",
                "No readable text was found, even after examining images in the document.",
            )
        raise UnsupportedDocument(
            "ocr_required",
            "No extractable text was found. This document needs OCR, which is switched off.",
        )
    return chunks

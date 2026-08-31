"""Shared helpers for the backend-independent contract."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import replace
from uuid import UUID

from haystack import Document
from primer_contracts.chunks import DocumentChunk
from primer_contracts.identity import Principal
from primer_contracts.retrieval import SourceLocator

#: Small on purpose. The contract under test is isolation and ranking order,
#: neither of which needs a production-sized vector, and every test pays for
#: the dimension in container time.
DIMENSIONS = 64

WORD = re.compile(r"[a-z0-9]+")


def embed_text(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    """A deterministic stand-in for an embedding endpoint.

    Words are hashed into a normalized bag-of-words vector. It is not a good
    embedding, but it is a real one: texts sharing words are close, texts
    sharing none are far, and it needs no network. What the conformance suite
    proves is that a backend filters and ranks what it is given, which does
    not depend on the vectors being clever.
    """
    vector = [0.0] * dimensions
    for word in WORD.findall(text.lower()):
        digest = hashlib.sha256(word.encode()).digest()
        vector[digest[0] % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        # An all-zero vector has no direction, and cosine distance against it
        # is undefined; every backend is entitled to reject or misrank it.
        return [1.0 / math.sqrt(dimensions)] * dimensions
    return [value / norm for value in vector]


class HashingDocumentEmbedder:
    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.dimensions = dimensions

    def run(self, documents: list[Document]) -> dict[str, object]:
        return {
            "documents": [
                replace(document, embedding=embed_text(document.content or "", self.dimensions))
                for document in documents
            ]
        }


class HashingTextEmbedder:
    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.dimensions = dimensions

    def run(self, text: str) -> dict[str, object]:
        return {"embedding": embed_text(text, self.dimensions)}


def principal_for(subject: str) -> Principal:
    return Principal(subject=subject, user_id=uuid.uuid5(uuid.NAMESPACE_URL, subject))


def make_chunk(
    *,
    library_id: UUID,
    generation_id: UUID,
    content: str,
    ordinal: int = 0,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> DocumentChunk:
    document_id = document_id or uuid.uuid5(uuid.NAMESPACE_URL, f"doc-{library_id}")
    version_id = version_id or uuid.uuid5(uuid.NAMESPACE_URL, f"ver-{library_id}")
    return DocumentChunk(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{generation_id}:{ordinal}"),
        ordinal=ordinal,
        library_id=library_id,
        document_id=document_id,
        document_version_id=version_id,
        owner_user_id=owner_user_id or uuid.uuid5(uuid.NAMESPACE_URL, "owner"),
        generation_id=generation_id,
        content=content,
        embedding_text=content,
        locator=SourceLocator(page=1, section="Findings"),
        filename="paper.pdf",
    )

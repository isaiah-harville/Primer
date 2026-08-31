"""Shared Primer cross-service wire models.

This package holds wire shapes only. It must not depend on any service,
database, or transport so producers and consumers can share one definition.
"""

from primer_contracts.base import WireModel
from primer_contracts.chat import ChatRequest, Citation
from primer_contracts.documents import DocumentSummary, IngestionStatus
from primer_contracts.errors import ErrorCode, ProblemDetail
from primer_contracts.identity import Principal
from primer_contracts.libraries import LibrarySummary
from primer_contracts.retrieval import RetrievalRequest, RetrievedChunk, SourceLocator

__all__ = [
    "ChatRequest",
    "Citation",
    "DocumentSummary",
    "ErrorCode",
    "IngestionStatus",
    "LibrarySummary",
    "Principal",
    "ProblemDetail",
    "RetrievalRequest",
    "RetrievedChunk",
    "SourceLocator",
    "WireModel",
]

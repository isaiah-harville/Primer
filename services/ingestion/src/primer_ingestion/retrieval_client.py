"""The worker's view of the Retrieval service.

Workers never touch a vector store. They hand chunks to Retrieval, which is
the only process that knows what backend is deployed or how it filters.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

import httpx2
from primer_contracts.chunks import DocumentChunk
from primer_contracts.identity import Principal
from primer_contracts.indexing import (
    DeleteRequest,
    DeleteResult,
    GenerationCount,
    GenerationQuery,
    IndexRequest,
    IndexResult,
)

from primer_ingestion.config import Settings

SERVICE_TOKEN_HEADER = "X-Primer-Service-Token"  # noqa: S105 - a header name, not a secret


class VectorIndex(Protocol):
    """What a stage needs from Retrieval, so a test can supply it."""

    def index(self, request: IndexRequest) -> IndexResult: ...

    def verify(self, request: GenerationQuery) -> GenerationCount: ...

    def delete(self, request: DeleteRequest) -> DeleteResult: ...


class RetrievalClient:
    def __init__(self, settings: Settings, client: httpx2.Client | None = None) -> None:
        token = settings.retrieval_token or settings.service_token
        self._client = client or httpx2.Client(
            base_url=settings.retrieval_url.rstrip("/"),
            # Generous, because embedding a batch is the slow part and a
            # timeout here costs a whole batch of work.
            timeout=settings.retrieval_timeout_seconds,
            headers=({SERVICE_TOKEN_HEADER: token.get_secret_value()} if token is not None else {}),
        )

    def __enter__(self) -> RetrievalClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._client.close()

    def _post(self, path: str, payload: object) -> dict[str, object]:
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        body: dict[str, object] = response.json()
        return body

    def index(self, request: IndexRequest) -> IndexResult:
        return IndexResult.model_validate(
            self._post("/internal/v1/index", request.model_dump(mode="json"))
        )

    def verify(self, request: GenerationQuery) -> GenerationCount:
        return GenerationCount.model_validate(
            self._post("/internal/v1/verify", request.model_dump(mode="json"))
        )

    def delete(self, request: DeleteRequest) -> DeleteResult:
        return DeleteResult.model_validate(
            self._post("/internal/v1/delete", request.model_dump(mode="json"))
        )


def worker_principal(owner_user_id: UUID) -> Principal:
    """Audit context for work done on a user's behalf, not authorization.

    The document's owner is named because that is whose data is being
    handled; the worker is not acting as them, and Retrieval does not treat
    this as permission to read anything.
    """
    return Principal(subject=f"ingestion-worker:{owner_user_id}", user_id=owner_user_id)


def batched(chunks: list[DocumentChunk], size: int) -> list[list[DocumentChunk]]:
    return [chunks[start : start + size] for start in range(0, len(chunks), size)]

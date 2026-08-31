"""The embed stage: chunks from the parse artifact into a pending generation.

Embedding happens inside Retrieval, not here. Retrieval owns the store and
therefore owns the vector width, the model, and the endpoint; a worker that
embedded independently could write vectors the store cannot compare.
"""

from __future__ import annotations

import logging

from primer_contracts.chunks import DocumentChunk
from primer_contracts.indexing import IndexRequest
from primer_contracts.ingestion import JobClaim
from primer_storage import ArtifactStore

from primer_ingestion.config import Settings
from primer_ingestion.errors import PermanentStageError
from primer_ingestion.retrieval_client import (
    RetrievalClient,
    VectorIndex,
    batched,
    worker_principal,
)
from primer_ingestion.stages.parse import CHUNKS_ARTIFACT

logger = logging.getLogger(__name__)


class EmbedStage:
    def __init__(
        self,
        settings: Settings,
        artifacts: ArtifactStore | None = None,
        index: VectorIndex | None = None,
    ) -> None:
        self._settings = settings
        self._artifacts = artifacts or ArtifactStore(settings.source_store_url)
        self._index = index or RetrievalClient(settings)

    def __call__(self, claim: JobClaim) -> None:
        chunks = self._load(claim)

        # Batched so one timeout costs one batch rather than a whole
        # document. Re-sending a batch is safe: chunk ids are derived, so a
        # repeated write overwrites the same rows.
        for batch in batched(chunks, self._settings.index_batch_size):
            self._index.index(
                IndexRequest(
                    principal=worker_principal(claim.owner_user_id),
                    library_id=claim.library_id,
                    document_version_id=claim.document_version_id,
                    generation_id=claim.generation_id,
                    chunks=tuple(batch),
                )
            )
        logger.info("job %s: indexed %d chunks", claim.job_id, len(chunks))

    def _load(self, claim: JobClaim) -> list[DocumentChunk]:
        try:
            payload = self._artifacts.read_json(
                claim.document_version_id, claim.generation_id, CHUNKS_ARTIFACT
            )
        except FileNotFoundError as error:
            # The parse stage completed, so this artifact should exist. If it
            # does not, this generation cannot be rebuilt from here and
            # retrying the embed stage forever would not help.
            raise PermanentStageError(
                "chunks_missing",
                "The parsed chunks for this generation are no longer available.",
            ) from error
        return [DocumentChunk.model_validate(item) for item in payload]

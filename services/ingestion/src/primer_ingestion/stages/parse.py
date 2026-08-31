"""The parse stage: source bytes in, scoped chunks out.

Chunks are written to the artifact store rather than returned, because the
stage that consumes them runs in a different process and receives only a job
id. Keying the artifact by generation means a rebuild writes a new file
instead of overwriting the one a running search still depends on.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from primer_contracts.ingestion import JobClaim, StageName
from primer_storage import ArtifactStore, SourceStore

from primer_ingestion.chunking import DocumentContext
from primer_ingestion.config import Settings
from primer_ingestion.errors import StageError
from primer_ingestion.parsing import DocumentParser

logger = logging.getLogger(__name__)

#: The artifact the embed stage reads.
CHUNKS_ARTIFACT = "chunks.json"


class ParseStage:
    """Holds the parser across jobs so Docling's models load once."""

    def __init__(
        self,
        settings: Settings,
        parser: DocumentParser | None = None,
        sources: SourceStore | None = None,
        artifacts: ArtifactStore | None = None,
    ) -> None:
        self._settings = settings
        self._parser = parser or DocumentParser(settings)
        self._sources = sources or SourceStore(
            settings.source_store_url, max_bytes=settings.max_source_bytes
        )
        self._artifacts = artifacts or ArtifactStore(settings.source_store_url)

    def __call__(self, claim: JobClaim) -> None:
        context = DocumentContext(
            owner_user_id=claim.owner_user_id,
            library_id=claim.library_id,
            document_id=claim.document_id,
            document_version_id=claim.document_version_id,
            generation_id=claim.generation_id,
            filename=claim.filename,
        )

        with TemporaryDirectory(prefix="primer-source-") as directory:
            local = Path(directory) / "source"
            try:
                self._sources.download(claim.source_sha256, local)
            except FileNotFoundError as error:
                # The metadata says these bytes are durable, so their absence
                # is an operational fault, not a bad document. Retrying is
                # right: object stores are eventually consistent and mounts
                # come back.
                raise StageError(
                    "source_unavailable", "The stored source could not be read."
                ) from error

            chunks = self._parser.parse_and_chunk(local, context, media_type=claim.media_type)

        self._artifacts.write_json(
            claim.document_version_id,
            claim.generation_id,
            CHUNKS_ARTIFACT,
            [chunk.model_dump(mode="json") for chunk in chunks],
        )
        logger.info(
            "job %s: parsed %s into %d chunks", claim.job_id, claim.document_id, len(chunks)
        )


def register(settings: Settings) -> None:
    """Attach the parse stage to the orchestrator."""
    from primer_ingestion.tasks import register_handler

    register_handler(StageName.PARSE, ParseStage(settings))

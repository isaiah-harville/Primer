"""The embed and index stages, against a recording Retrieval."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from primer_contracts.indexing import (
    DeleteRequest,
    DeleteResult,
    GenerationCount,
    GenerationQuery,
    IndexRequest,
    IndexResult,
    PurgeRequest,
)
from primer_contracts.ingestion import JobClaim, StageName
from primer_ingestion.config import Settings
from primer_ingestion.errors import PermanentStageError, StageError
from primer_ingestion.stages.embed import EmbedStage
from primer_ingestion.stages.index import IndexStage
from primer_ingestion.stages.parse import CHUNKS_ARTIFACT
from primer_storage import ArtifactStore

VERSION = uuid.uuid5(uuid.NAMESPACE_URL, "version")
GENERATION = uuid.uuid5(uuid.NAMESPACE_URL, "generation")
LIBRARY = uuid.uuid5(uuid.NAMESPACE_URL, "library")


class RecordingIndex:
    """A Retrieval that records what it was asked to store."""

    def __init__(self, reported_count: int | None = None) -> None:
        self.requests: list[IndexRequest] = []
        self.purges: list[PurgeRequest] = []
        self.reported_count = reported_count

    @property
    def stored(self) -> int:
        return sum(len(request.chunks) for request in self.requests)

    def index(self, request: IndexRequest) -> IndexResult:
        self.requests.append(request)
        return IndexResult(generation_id=request.generation_id, written=len(request.chunks))

    def verify(self, request: GenerationQuery) -> GenerationCount:
        count = self.reported_count if self.reported_count is not None else self.stored
        return GenerationCount(generation_id=request.generation_id, count=count)

    def delete(self, request: DeleteRequest) -> DeleteResult:
        return DeleteResult(generation_id=request.generation_id, deleted=0)

    def purge(self, request: PurgeRequest) -> DeleteResult:
        self.purges.append(request)
        return DeleteResult(
            generation_id=request.keep_generation_id or request.document_version_id, deleted=0
        )


def chunk_payload(ordinal: int) -> dict[str, object]:
    return {
        "chunk_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{VERSION}:{GENERATION}:{ordinal}")),
        "ordinal": ordinal,
        "library_id": str(LIBRARY),
        "document_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "document")),
        "document_version_id": str(VERSION),
        "owner_user_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "owner")),
        "generation_id": str(GENERATION),
        "content": f"passage {ordinal}",
        "embedding_text": f"Findings\npassage {ordinal}",
        "locator": {"page": 1, "section": "Findings"},
        "filename": "paper.pdf",
    }


@pytest.fixture
def claim() -> JobClaim:
    return JobClaim(
        job_id=uuid.uuid5(uuid.NAMESPACE_URL, "job"),
        stage=StageName.EMBED,
        generation_id=GENERATION,
        attempt=1,
        document_id=uuid.uuid5(uuid.NAMESPACE_URL, "document"),
        document_version_id=VERSION,
        library_id=LIBRARY,
        owner_user_id=uuid.uuid5(uuid.NAMESPACE_URL, "owner"),
        source_sha256="c" * 64,
        filename="paper.pdf",
        media_type="application/pdf",
        byte_size=2048,
    )


@pytest.fixture
def artifacts(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(f"file://{tmp_path}")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(source_store_url=f"file://{tmp_path}", index_batch_size=2)


def write_chunks(artifacts: ArtifactStore, count: int) -> None:
    artifacts.write_json(
        VERSION, GENERATION, CHUNKS_ARTIFACT, [chunk_payload(n) for n in range(count)]
    )


def test_every_chunk_reaches_retrieval_with_its_scope(
    settings: Settings, artifacts: ArtifactStore, claim: JobClaim
) -> None:
    write_chunks(artifacts, 5)
    index = RecordingIndex()

    EmbedStage(settings, artifacts=artifacts, index=index)(claim)

    assert index.stored == 5
    assert all(request.library_id == LIBRARY for request in index.requests)
    assert all(request.generation_id == GENERATION for request in index.requests)


def test_chunks_are_sent_in_bounded_batches(
    settings: Settings, artifacts: ArtifactStore, claim: JobClaim
) -> None:
    """One timeout should cost a batch, not a whole document."""
    write_chunks(artifacts, 5)
    index = RecordingIndex()

    EmbedStage(settings, artifacts=artifacts, index=index)(claim)

    assert [len(request.chunks) for request in index.requests] == [2, 2, 1]


def test_embedding_without_parsed_chunks_fails_permanently(
    settings: Settings, artifacts: ArtifactStore, claim: JobClaim
) -> None:
    """Parse said it finished; if its output is gone, retrying cannot restore it."""
    with pytest.raises(PermanentStageError) as raised:
        EmbedStage(settings, artifacts=artifacts, index=RecordingIndex())(claim)
    assert raised.value.code == "chunks_missing"


def test_a_complete_generation_passes_verification(
    settings: Settings, artifacts: ArtifactStore, claim: JobClaim
) -> None:
    write_chunks(artifacts, 3)
    index = RecordingIndex(reported_count=3)

    IndexStage(settings, artifacts=artifacts, index=index)(claim)


def test_a_short_generation_is_refused_and_retried(
    settings: Settings, artifacts: ArtifactStore, claim: JobClaim
) -> None:
    """Activating a short index would drop passages from every future answer."""
    write_chunks(artifacts, 3)
    index = RecordingIndex(reported_count=2)

    with pytest.raises(StageError) as raised:
        IndexStage(settings, artifacts=artifacts, index=index)(claim)

    assert raised.value.code == "incomplete_index"
    assert type(raised.value) is StageError


def test_the_worker_registers_a_handler_for_every_pipeline_stage() -> None:
    """A missing handler would fail documents for a deployment reason."""
    from primer_ingestion.tasks import HANDLERS
    from primer_ingestion.worker import register_stages

    register_stages(Settings())

    assert {StageName.PARSE, StageName.EMBED, StageName.INDEX} <= set(HANDLERS)

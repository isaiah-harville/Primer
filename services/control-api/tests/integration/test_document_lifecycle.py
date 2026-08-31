"""Reindex and deletion, including the moments they overlap.

The cases here are the ones where being approximately right means a user
sees the wrong thing: an old index emptied before the new one is live, a
deleted document still answering, or bytes removed while another library
still points at them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import pytest_asyncio
from control_support import ServiceClient, UserClient
from primer_control.db import Database
from primer_control.models import Document, DocumentVersion, IngestionJob, SourceObject
from sqlalchemy import func, select


@dataclass(frozen=True)
class Uploaded:
    document_id: str
    job_id: str
    generation_id: str


async def job_row(database: Database, document_id: str) -> IngestionJob:
    async with database.session() as session:
        result = await session.execute(
            select(IngestionJob)
            .join(DocumentVersion, IngestionJob.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
        )
        job = result.scalars().first()
    assert job is not None
    return job


async def upload(
    owner: UserClient,
    library_id: str,
    database: Database,
    name: str = "paper.txt",
    content: bytes = b"evidence",
) -> Uploaded:
    document = (await owner.upload(library_id, name, content)).json()
    job = await job_row(database, document["id"])
    return Uploaded(document["id"], str(job.id), str(job.generation_id))


async def take_to_ready(service: ServiceClient, job: Uploaded) -> None:
    for stage in ("parse", "embed", "index"):
        await service.claim(job.job_id, stage)
        await service.complete(job.job_id, job.generation_id, stage)


@pytest_asyncio.fixture
async def indexed(
    owner: UserClient, service: ServiceClient, library_id: str, database: Database
) -> Uploaded:
    job = await upload(owner, library_id, database)
    await take_to_ready(service, job)
    return job


def generations_path(library_id: str) -> str:
    return f"/internal/v1/ingestion/libraries/{library_id}/generations"


async def test_the_old_generation_answers_until_the_new_one_activates(
    owner: UserClient,
    service: ServiceClient,
    library_id: str,
    database: Database,
    indexed: Uploaded,
) -> None:
    """A rebuild must not create a window where the document answers nothing."""
    path = f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}"
    started = await owner.post(f"{path}/reindex", {})
    assert started.status_code == 202

    rebuilt = await job_row(database, indexed.document_id)
    assert str(rebuilt.generation_id) != indexed.generation_id
    assert (await service.get(generations_path(library_id))).json() == [indexed.generation_id]

    for stage in ("parse", "embed", "index"):
        await service.claim(indexed.job_id, stage)
        await service.complete(indexed.job_id, str(rebuilt.generation_id), stage)

    assert (await service.get(generations_path(library_id))).json() == [str(rebuilt.generation_id)]


async def test_reindexing_twice_does_not_start_two_builds(
    owner: UserClient, library_id: str, database: Database, indexed: Uploaded
) -> None:
    """Two builds of one version would leave one of them permanently orphaned."""
    path = f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}/reindex"

    first = await owner.post(path, {})
    after_first = await job_row(database, indexed.document_id)
    second = await owner.post(path, {})
    after_second = await job_row(database, indexed.document_id)

    assert first.status_code == second.status_code == 202
    assert after_first.generation_id == after_second.generation_id


async def test_a_failed_reindex_leaves_the_old_generation_serving(
    owner: UserClient,
    service: ServiceClient,
    library_id: str,
    database: Database,
    indexed: Uploaded,
) -> None:
    """Nothing is lost by a rebuild that never finishes."""
    await owner.post(f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}/reindex", {})
    rebuilt = await job_row(database, indexed.document_id)

    await service.claim(indexed.job_id, "parse")
    await service.fail(
        indexed.job_id, str(rebuilt.generation_id), code="ocr_required", disposition="unsupported"
    )

    assert (await service.get(generations_path(library_id))).json() == [indexed.generation_id]


async def test_a_reindex_can_be_started_again_after_it_fails(
    owner: UserClient,
    service: ServiceClient,
    library_id: str,
    database: Database,
    indexed: Uploaded,
) -> None:
    """A terminal state is what makes the button work a second time."""
    path = f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}/reindex"
    await owner.post(path, {})
    failed = await job_row(database, indexed.document_id)
    await service.claim(indexed.job_id, "parse")
    await service.fail(
        indexed.job_id, str(failed.generation_id), code="stage_error", disposition="failed"
    )

    await owner.post(path, {})
    retried = await job_row(database, indexed.document_id)

    assert retried.generation_id != failed.generation_id
    assert retried.state == "queued"


async def test_deletion_stops_retrieval_before_any_cleanup_runs(
    owner: UserClient, service: ServiceClient, library_id: str, indexed: Uploaded
) -> None:
    """The tombstone is the deletion; the cleanup is bookkeeping."""
    await owner.delete(f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}")

    assert (await service.get(generations_path(library_id))).json() == []


async def test_purging_removes_the_rows_and_frees_the_source(
    owner: UserClient,
    service: ServiceClient,
    library_id: str,
    database: Database,
    indexed: Uploaded,
) -> None:
    await owner.delete(f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}")

    freed = await service.purge(indexed.job_id)

    assert freed.status_code == 200
    assert len(freed.json()) == 1
    async with database.session() as session:
        documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        sources = (
            await session.execute(select(func.count()).select_from(SourceObject))
        ).scalar_one()
    assert documents == 0
    assert sources == 0


async def test_purging_twice_frees_nothing_the_second_time(
    owner: UserClient, service: ServiceClient, library_id: str, indexed: Uploaded
) -> None:
    """A redelivered cleanup message must be finishable, not an error."""
    await owner.delete(f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}")
    await service.purge(indexed.job_id)

    repeated = await service.purge(indexed.job_id)

    assert repeated.status_code == 404


async def test_shared_bytes_survive_one_document_being_deleted(
    owner: UserClient, service: ServiceClient, library_id: str, database: Database
) -> None:
    """Deduplication must never let one user's delete erase another's document."""
    first = await upload(owner, library_id, database, "one.txt", b"identical evidence")
    second = await upload(owner, library_id, database, "two.txt", b"identical evidence")

    await owner.delete(f"/api/v1/libraries/{library_id}/documents/{first.document_id}")
    freed = (await service.purge(first.job_id)).json()

    assert freed == []
    async with database.session() as session:
        sources = (
            await session.execute(select(func.count()).select_from(SourceObject))
        ).scalar_one()
    assert sources == 1
    survivor = await owner.get(
        f"/api/v1/libraries/{library_id}/documents/{second.document_id}/content"
    )
    assert survivor.content == b"identical evidence"


async def test_the_last_document_holding_bytes_frees_them(
    owner: UserClient, service: ServiceClient, library_id: str, database: Database
) -> None:
    first = await upload(owner, library_id, database, "one.txt", b"identical evidence")
    second = await upload(owner, library_id, database, "two.txt", b"identical evidence")

    for job in (first, second):
        await owner.delete(f"/api/v1/libraries/{library_id}/documents/{job.document_id}")
    freed_first = (await service.purge(first.job_id)).json()
    freed_second = (await service.purge(second.job_id)).json()

    assert freed_first == []
    assert len(freed_second) == 1


async def test_a_live_document_cannot_be_purged(service: ServiceClient, indexed: Uploaded) -> None:
    """The tombstone is the guard: without one there is nothing to clean up."""
    assert (await service.purge(indexed.job_id)).status_code == 404


@pytest.mark.parametrize("action", ["reindex", "delete"])
async def test_a_stranger_cannot_reindex_or_delete(
    stranger: UserClient, library_id: str, indexed: Uploaded, action: str
) -> None:
    path = f"/api/v1/libraries/{library_id}/documents/{indexed.document_id}"
    response = (
        await stranger.post(f"{path}/reindex", {})
        if action == "reindex"
        else await stranger.delete(path)
    )
    assert response.status_code == 404

"""Document, version, and job persistence.

Authorization is not decided here. Every read takes a library predicate from
LibraryAccess and joins through `libraries`, so a document is reachable only
when its library is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from primer_contracts.documents import IngestionStatus
from primer_storage import StoredSource
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import Document, DocumentVersion, IngestionJob, Library, SourceObject


@dataclass(frozen=True)
class DocumentRecord:
    """A document with the version a user currently sees and its job state."""

    document: Document
    version: DocumentVersion
    job: IngestionJob | None


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_source(self, stored: StoredSource) -> None:
        """Record the source object unless these bytes are already known.

        Two uploads of the same content race here, so this is an upsert
        rather than a read-then-insert. The row is immutable, so the loser of
        the race has nothing to update.
        """
        statement = (
            insert(SourceObject)
            .values(
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type=stored.media_type,
            )
            .on_conflict_do_nothing(index_elements=[SourceObject.sha256])
        )
        await self._session.execute(statement)

    async def create_document(self, *, library_id: UUID) -> Document:
        document = Document(id=uuid.uuid4(), library_id=library_id)
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def add_version(
        self, document: Document, stored: StoredSource, *, filename: str
    ) -> DocumentVersion:
        """Append an immutable version, numbered after the document's latest."""
        highest = await self._session.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document.id,
            version_number=(highest.scalar() or 0) + 1,
            source_sha256=stored.sha256,
            filename=filename,
            media_type=stored.media_type,
            byte_size=stored.byte_size,
        )
        self._session.add(version)
        document.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(version)
        return version

    async def enqueue_job(self, version: DocumentVersion) -> IngestionJob:
        """Record the work of indexing a version, in its own generation.

        The row is created here and claimed by a worker later; nothing is
        published to the broker inside this transaction, so a rolled-back
        upload cannot leave a message pointing at a version that never
        existed.
        """
        job = IngestionJob(
            id=uuid.uuid4(),
            document_version_id=version.id,
            generation_id=uuid.uuid4(),
            state=IngestionStatus.QUEUED.value,
        )
        self._session.add(job)
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def _records(self, documents: list[Document]) -> list[DocumentRecord]:
        """Attach each document's current version and latest job."""
        if not documents:
            return []
        document_ids = [document.id for document in documents]

        versions = await self._session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(document_ids))
            .distinct(DocumentVersion.document_id)
            .order_by(DocumentVersion.document_id, DocumentVersion.version_number.desc())
        )
        current = {version.document_id: version for version in versions.scalars()}

        jobs = await self._session.execute(
            select(IngestionJob)
            .where(IngestionJob.document_version_id.in_([v.id for v in current.values()]))
            .distinct(IngestionJob.document_version_id)
            .order_by(
                IngestionJob.document_version_id,
                IngestionJob.created_at.desc(),
                IngestionJob.id.desc(),
            )
        )
        latest = {job.document_version_id: job for job in jobs.scalars()}

        records = []
        for document in documents:
            version = current.get(document.id)
            # A document with no version was interrupted mid-upload; it has
            # nothing a user could read, so it is not listed.
            if version is None:
                continue
            records.append(DocumentRecord(document, version, latest.get(version.id)))
        return records

    async def find_all(
        self, *, library_id: UUID, where: ColumnElement[bool]
    ) -> list[DocumentRecord]:
        result = await self._session.execute(
            select(Document)
            .join(Library, Document.library_id == Library.id)
            .where(
                Document.library_id == library_id,
                Document.deleted_at.is_(None),
                Library.deleted_at.is_(None),
                where,
            )
            .order_by(Document.created_at, Document.id)
        )
        return await self._records(list(result.scalars()))

    async def get(
        self, document_id: UUID, *, library_id: UUID, where: ColumnElement[bool]
    ) -> DocumentRecord | None:
        result = await self._session.execute(
            select(Document)
            .join(Library, Document.library_id == Library.id)
            .where(
                Document.id == document_id,
                Document.library_id == library_id,
                Document.deleted_at.is_(None),
                Library.deleted_at.is_(None),
                where,
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            return None
        records = await self._records([document])
        return records[0] if records else None

    async def soft_delete(self, document: Document) -> None:
        """Tombstone first; vector and source cleanup follow asynchronously."""
        document.deleted_at = datetime.now(UTC)
        await self._session.flush()

"""Library persistence. Authorization predicates come from LibraryAccess."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import Document, DocumentVersion, Library


class LibraryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str, owner_user_id: UUID) -> Library:
        library = Library(id=uuid.uuid4(), name=name, owner_user_id=owner_user_id)
        self._session.add(library)
        await self._session.flush()
        await self._session.refresh(library)
        return library

    async def get(self, library_id: UUID, *, where: ColumnElement[bool]) -> Library | None:
        """Fetch one live library matching an authorization predicate."""
        result = await self._session.execute(
            select(Library).where(Library.id == library_id, Library.deleted_at.is_(None), where)
        )
        return result.scalar_one_or_none()

    async def find_all(self, *, where: ColumnElement[bool]) -> list[Library]:
        result = await self._session.execute(
            select(Library)
            .where(Library.deleted_at.is_(None), where)
            .order_by(Library.created_at, Library.id)
        )
        return list(result.scalars())

    async def document_counts(self, library_ids: Sequence[UUID]) -> dict[UUID, int]:
        """How many documents each library holds, as a user would count them.

        Counted here rather than derived from a stored column, because a
        cached count is a second source of truth that drifts the first time
        an upload is rolled back or a delete is retried.

        The definition has to match what listing a library returns, or the
        two disagree and one of them looks like data loss: live documents
        only, and only those with a version behind them. A document with no
        version was interrupted mid-upload and has nothing anyone could
        read, so it is not listed and must not be counted either.
        """
        if not library_ids:
            return {}
        has_version = exists().where(DocumentVersion.document_id == Document.id)
        result = await self._session.execute(
            select(Document.library_id, func.count().label("documents"))
            .where(
                Document.library_id.in_(library_ids),
                Document.deleted_at.is_(None),
                has_version,
            )
            .group_by(Document.library_id)
        )
        counted: dict[UUID, int] = {row.library_id: row.documents for row in result.all()}
        # Every library asked about gets an answer: a library with no
        # documents is absent from the grouped result, and leaving it out
        # would make the caller guess between "none" and "not counted".
        return {library_id: counted.get(library_id, 0) for library_id in library_ids}

    async def rename(self, library: Library, name: str) -> Library:
        library.name = name
        await self._session.flush()
        await self._session.refresh(library)
        return library

    async def soft_delete(self, library: Library) -> None:
        library.deleted_at = datetime.now(UTC)
        await self._session.flush()

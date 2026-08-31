"""Library persistence. Authorization predicates come from LibraryAccess."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import Library


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

    async def rename(self, library: Library, name: str) -> Library:
        library.name = name
        await self._session.flush()
        await self._session.refresh(library)
        return library

    async def soft_delete(self, library: Library) -> None:
        library.deleted_at = datetime.now(UTC)
        await self._session.flush()

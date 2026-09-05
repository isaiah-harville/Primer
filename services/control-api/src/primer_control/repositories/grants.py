"""Library grant persistence.

Who may read a library is decided by `LibraryAccess`; this only writes and
reads the rows that decision consults.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import LibraryGrant, User


class LibraryGrantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live(self, library_id: UUID, grantee_user_id: UUID) -> LibraryGrant | None:
        """The grant in force for this person, if there is one."""
        result = await self._session.execute(
            select(LibraryGrant).where(
                LibraryGrant.library_id == library_id,
                LibraryGrant.grantee_user_id == grantee_user_id,
                LibraryGrant.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def grant(
        self, *, library_id: UUID, grantee_user_id: UUID, granted_by_user_id: UUID
    ) -> LibraryGrant:
        """Share the library, or return the share that already exists.

        Idempotent, because the interesting question a caller is asking is
        "may this person read it" and the answer after two identical
        requests is the same as after one. A second grant that raised would
        make a double-clicked button look like a failure.
        """
        existing = await self.live(library_id, grantee_user_id)
        if existing is not None:
            return existing

        grant = LibraryGrant(
            id=uuid.uuid4(),
            library_id=library_id,
            grantee_user_id=grantee_user_id,
            granted_by_user_id=granted_by_user_id,
        )
        self._session.add(grant)
        await self._session.flush()
        await self._session.refresh(grant)
        return grant

    async def revoke(self, grant: LibraryGrant) -> None:
        """Stamp the grant revoked.

        There is nothing else to do. `LibraryAccess` reads this column on
        every request, so the next one the grantee makes is already refused
        - no cache to clear, no index to rewrite, and no vectors to move,
        since a shared library was never a copy of anything.
        """
        grant.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def shared_with(self, library_id: UUID) -> list[tuple[LibraryGrant, User]]:
        """Everyone the library is shared with now, oldest share first.

        Joined to the user rather than returning ids: the owner reviewing
        this list is checking it against people they know, and an id is not
        something anyone can check an intention against.
        """
        result = await self._session.execute(
            select(LibraryGrant, User)
            .join(User, User.id == LibraryGrant.grantee_user_id)
            .where(
                LibraryGrant.library_id == library_id,
                LibraryGrant.revoked_at.is_(None),
            )
            .order_by(LibraryGrant.created_at, LibraryGrant.id)
        )
        return [(grant, user) for grant, user in result.all()]

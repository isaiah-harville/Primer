"""User persistence."""

from __future__ import annotations

from primer_contracts.identity import Principal
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, principal: Principal) -> None:
        """Record the principal's user row if this subject is new.

        User ids are derived from the OIDC subject, so this upsert only
        materializes a row the first time a known identity writes something.
        Concurrent first requests race, hence ON CONFLICT DO NOTHING rather
        than a read-then-insert.
        """
        statement = (
            insert(User)
            .values(
                id=principal.user_id,
                subject=principal.subject,
                email=principal.email,
                display_name=principal.display_name,
            )
            .on_conflict_do_nothing(index_elements=[User.subject])
        )
        await self._session.execute(statement)

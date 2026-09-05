"""User persistence."""

from __future__ import annotations

from uuid import UUID

from primer_contracts.identity import Principal
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, principal: Principal) -> None:
        """Record the principal's user row, and keep what it says current.

        User ids are derived from the OIDC subject, so this upsert only
        materializes a row the first time a known identity writes something.
        Concurrent first requests race, hence an upsert rather than a
        read-then-insert.

        It updates as well as inserts, which it did not always do. Recording
        the address only on a user's very first write left it wrong forever
        afterwards: someone who used Primer before the provider was
        configured to send the claim had no address on file, and sharing
        names people by address - so they could never be shared with, and
        nothing on screen explained why.

        A missing claim never erases a known value. Coalescing rather than
        assigning means a deployment that stops sending the header degrades
        to stale addresses instead of wiping every one of them, which is the
        difference between sharing being out of date and sharing being
        impossible.

        The `where` clause keeps this from writing on every request. Without
        it each library creation would touch the row and move `updated_at`
        for nothing.
        """
        insertion = insert(User).values(
            id=principal.user_id,
            subject=principal.subject,
            email=principal.email,
            display_name=principal.display_name,
        )
        email = func.coalesce(insertion.excluded.email, User.email)
        display_name = func.coalesce(insertion.excluded.display_name, User.display_name)
        await self._session.execute(
            insertion.on_conflict_do_update(
                index_elements=[User.subject],
                set_={"email": email, "display_name": display_name},
                where=or_(
                    User.email.is_distinct_from(email),
                    User.display_name.is_distinct_from(display_name),
                ),
            )
        )

    async def find_by_email(self, email: str) -> list[User]:
        """Everyone signed in under this address.

        A list rather than one row, because nothing guarantees there is one.
        `users.email` comes from the identity provider and is neither unique
        nor required: two subjects can carry the same address, and a
        deployment whose provider omits the claim has none at all. A caller
        that took the first row would share a private library with whichever
        account happened to sort first, which is not a mistake anyone would
        notice until it mattered.

        Compared case-insensitively. Addresses are handed round in whatever
        case people type them, and refusing to match `A@example.edu` against
        `a@example.edu` would look like the person not existing.
        """
        result = await self._session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        return list(result.scalars())

    async def find(self, user_id: UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

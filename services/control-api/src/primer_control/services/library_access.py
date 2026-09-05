"""The single place library authorization is decided.

Routes and repositories never compare `owner_user_id` themselves. Every
decision passes through this service, so the sharing model changes one
policy object instead of every caller, and the HTTP and retrieval contracts
stay unchanged.
"""

from __future__ import annotations

from uuid import UUID

from primer_control.models import Library, LibraryGrant
from sqlalchemy import ColumnElement, or_, select


class LibraryAccess:
    """Who may read a library, and who may change it.

    Reading is the owner or anyone holding a live grant. Changing it is the
    owner, and only the owner: renaming, deleting, uploading, replacing,
    reindexing and sharing are all the owner's, because a share says nothing
    about what else the person may do. Roles are a separate design, and
    until there is one the honest reading of "shared" is "may read".

    `readable` and `manageable` return SQL predicates rather than booleans so
    that listing applies the same policy as a single-resource check. That is
    what keeps a shared library out of exactly the same places a private one
    is kept out of, without either rule being written down twice.
    """

    def readable(self, principal_id: UUID) -> ColumnElement[bool]:
        return or_(
            Library.owner_user_id == principal_id,
            # A subquery rather than a join: `readable` is dropped into
            # `where` clauses that already select from `libraries`, and a
            # join would multiply their rows by the number of grants and
            # silently list a library once per person it is shared with.
            Library.id.in_(
                select(LibraryGrant.library_id).where(
                    LibraryGrant.grantee_user_id == principal_id,
                    LibraryGrant.revoked_at.is_(None),
                )
            ),
        )

    def manageable(self, principal_id: UUID) -> ColumnElement[bool]:
        return or_(Library.owner_user_id == principal_id)

"""The single place library authorization is decided.

Routes and repositories never compare `owner_user_id` themselves. Every
decision passes through this service, so a future sharing model changes one
policy object instead of every caller, and the HTTP and retrieval contracts
stay unchanged.
"""

from __future__ import annotations

from uuid import UUID

from primer_control.models import Library
from sqlalchemy import ColumnElement, or_


class LibraryAccess:
    """MVP policy: only the owner may read or manage a library.

    `readable` and `manageable` return SQL predicates rather than booleans so
    listing applies the same policy as a single-resource check. A future
    grant table becomes an extra OR clause here.
    """

    def readable(self, principal_id: UUID) -> ColumnElement[bool]:
        return or_(Library.owner_user_id == principal_id)

    def manageable(self, principal_id: UUID) -> ColumnElement[bool]:
        return or_(Library.owner_user_id == principal_id)

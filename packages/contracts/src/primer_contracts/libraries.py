"""Library contracts.

A library has one owner, and `owner_user_id` is reported alongside the
acting principal rather than standing in for authorization: a caller
compares the two to tell its own libraries from ones shared with it, and
never to decide what it may do with either. Control decides that.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel

LibraryName = Annotated[str, Field(min_length=1, max_length=120)]


class LibrarySummary(WireModel):
    """A library as returned by the Control API."""

    id: UUID
    name: LibraryName
    owner_user_id: UUID
    document_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class LibraryShare(WireModel):
    """One person a library has been shared with.

    Identified by email as well as by id, because an id is not something the
    owner can check their intent against. Sharing is a decision about a
    person, and the owner has to be able to see that the person on the list
    is the one they meant.

    Deliberately carries no role. Read access is the only thing a share
    grants today, and a field named `role` that always says the same word
    would be a promise the authorization model does not keep.
    """

    user_id: UUID
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)
    #: When the share was made, so an owner reviewing a list can tell a
    #: decision they remember from one they do not.
    created_at: datetime

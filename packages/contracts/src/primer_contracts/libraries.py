"""Library contracts.

MVP libraries have a single owner, but `owner_user_id` is reported alongside
the acting principal rather than standing in for authorization, so a future
membership model does not change this shape.
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

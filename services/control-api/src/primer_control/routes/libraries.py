"""Library CRUD.

Inaccessible libraries return 404, never 403: telling a stranger that a
library exists but is not theirs is itself a disclosure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from primer_contracts.errors import ErrorCode
from primer_contracts.libraries import LibrarySummary
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.db import get_session
from primer_control.errors import ProblemError
from primer_control.identity import CurrentPrincipal
from primer_control.models import Library
from primer_control.repositories.libraries import LibraryRepository
from primer_control.repositories.users import UserRepository
from primer_control.services.library_access import LibraryAccess

router = APIRouter(prefix="/api/v1/libraries", tags=["libraries"])

Session = Annotated[AsyncSession, Depends(get_session)]
access = LibraryAccess()


class LibraryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class LibraryUpdate(LibraryCreate):
    #: Optimistic concurrency: when supplied, a rename only applies if the
    #: caller saw the current state, so two editors cannot silently overwrite
    #: each other.
    expected_updated_at: datetime | None = None


def not_found() -> ProblemError:
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title="Library not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No library with that identifier is available to you.",
    )


def summarize(library: Library) -> LibrarySummary:
    return LibrarySummary(
        id=library.id,
        name=library.name,
        owner_user_id=library.owner_user_id,
        created_at=library.created_at,
        updated_at=library.updated_at,
    )


@router.get("", summary="List the caller's libraries")
async def list_libraries(principal: CurrentPrincipal, session: Session) -> list[LibrarySummary]:
    libraries = await LibraryRepository(session).find_all(where=access.readable(principal.user_id))
    return [summarize(library) for library in libraries]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a private library")
async def create_library(
    payload: LibraryCreate, principal: CurrentPrincipal, session: Session
) -> LibrarySummary:
    await UserRepository(session).ensure(principal)
    library = await LibraryRepository(session).create(
        name=payload.name, owner_user_id=principal.user_id
    )
    return summarize(library)


@router.get("/{library_id}", summary="Read one library")
async def read_library(
    library_id: UUID, principal: CurrentPrincipal, session: Session
) -> LibrarySummary:
    library = await LibraryRepository(session).get(
        library_id, where=access.readable(principal.user_id)
    )
    if library is None:
        raise not_found()
    return summarize(library)


@router.patch("/{library_id}", summary="Rename a library")
async def rename_library(
    library_id: UUID, payload: LibraryUpdate, principal: CurrentPrincipal, session: Session
) -> LibrarySummary:
    repository = LibraryRepository(session)
    library = await repository.get(library_id, where=access.manageable(principal.user_id))
    if library is None:
        raise not_found()

    if (
        payload.expected_updated_at is not None
        and library.updated_at != payload.expected_updated_at
    ):
        raise ProblemError(
            code=ErrorCode.CONFLICT,
            title="Library changed since it was read",
            status_code=status.HTTP_409_CONFLICT,
            detail="Reload the library and reapply the change.",
        )

    return summarize(await repository.rename(library, payload.name))


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a library")
async def delete_library(
    library_id: UUID, principal: CurrentPrincipal, session: Session
) -> Response:
    repository = LibraryRepository(session)
    library = await repository.get(library_id, where=access.manageable(principal.user_id))
    if library is None:
        raise not_found()
    await repository.soft_delete(library)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

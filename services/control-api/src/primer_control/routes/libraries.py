"""Library CRUD.

Inaccessible libraries return 404, never 403: telling a stranger that a
library exists but is not theirs is itself a disclosure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from primer_contracts.errors import ErrorCode
from primer_contracts.ingestion import StageName
from primer_contracts.libraries import LibrarySummary
from primer_service.db import get_session
from primer_service.durable import DurableRoute
from primer_service.errors import ProblemError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.identity import CurrentPrincipal
from primer_control.models import Library
from primer_control.publisher import JobPublisher
from primer_control.repositories.libraries import LibraryRepository
from primer_control.repositories.users import UserRepository
from primer_control.services.duplication import LibraryDuplicator, copy_name
from primer_control.services.library_access import LibraryAccess

router = APIRouter(prefix="/api/v1/libraries", tags=["libraries"], route_class=DurableRoute)

Session = Annotated[AsyncSession, Depends(get_session)]


def get_publisher(request: Request) -> JobPublisher:
    publisher: JobPublisher = request.app.state.publisher
    return publisher


Publisher = Annotated[JobPublisher, Depends(get_publisher)]
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


def summarize(library: Library, document_count: int) -> LibrarySummary:
    """Describe a library, including how much is in it.

    The count is a parameter rather than a default, because the web app
    prints it everywhere a library is named and a library that silently
    reported zero would look like one that had lost its documents.
    """
    return LibrarySummary(
        id=library.id,
        name=library.name,
        owner_user_id=library.owner_user_id,
        document_count=document_count,
        created_at=library.created_at,
        updated_at=library.updated_at,
    )


async def summarize_one(repository: LibraryRepository, library: Library) -> LibrarySummary:
    counts = await repository.document_counts([library.id])
    return summarize(library, counts[library.id])


@router.get("", summary="List the caller's libraries")
async def list_libraries(principal: CurrentPrincipal, session: Session) -> list[LibrarySummary]:
    repository = LibraryRepository(session)
    libraries = await repository.find_all(where=access.readable(principal.user_id))
    # One grouped query for the whole list rather than one per library: this
    # is the layout's load on every page, not a detail view.
    counts = await repository.document_counts([library.id for library in libraries])
    return [summarize(library, counts[library.id]) for library in libraries]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a private library")
async def create_library(
    payload: LibraryCreate, principal: CurrentPrincipal, session: Session
) -> LibrarySummary:
    await UserRepository(session).ensure(principal)
    library = await LibraryRepository(session).create(
        name=payload.name, owner_user_id=principal.user_id
    )
    return summarize(library, document_count=0)


class LibraryDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: Optional. Left out, the copy is named after the original.
    name: str | None = Field(default=None, min_length=1, max_length=120)


@router.post(
    "/{library_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    summary="Copy a library into a new one",
)
async def duplicate_library(
    library_id: UUID,
    payload: LibraryDuplicate,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    session: Session,
    publisher: Publisher,
) -> LibrarySummary:
    """Copy a library so the two can diverge.

    The copy is owned by whoever asked for it, not by whoever owned the
    original: a copy of something you were allowed to read is yours, and
    leaving it owned by someone else would make it unmanageable by the only
    person who knows it exists.

    Its documents are queued for indexing like any upload, so the copy is
    browsable immediately and answerable once they finish. Nothing is
    published to the broker until the transaction commits.
    """
    await UserRepository(session).ensure(principal)
    repository = LibraryRepository(session)
    readable = access.readable(principal.user_id)
    source = await repository.get(library_id, where=readable)
    if source is None:
        raise not_found()

    duplication = await LibraryDuplicator(session).duplicate(
        source,
        name=payload.name or copy_name(source.name),
        owner_user_id=principal.user_id,
        where=readable,
    )
    for job in duplication.jobs:
        background.add_task(publisher.publish, StageName.PARSE, job.id)
    return await summarize_one(repository, duplication.library)


@router.get("/{library_id}", summary="Read one library")
async def read_library(
    library_id: UUID, principal: CurrentPrincipal, session: Session
) -> LibrarySummary:
    repository = LibraryRepository(session)
    library = await repository.get(library_id, where=access.readable(principal.user_id))
    if library is None:
        raise not_found()
    return await summarize_one(repository, library)


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

    return await summarize_one(repository, await repository.rename(library, payload.name))


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

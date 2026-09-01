"""Copying a library so one copy can change without the other.

Only the current version of each document is carried over. A duplicate is a
new starting point rather than a second copy of a history: bringing every
past version would reproduce replacements the user made in the original,
which is the opposite of wanting to diverge from it.

The bytes are not copied at all. Source objects are addressed by content and
shared already, so a duplicate references the same stored blobs and costs
nothing on disk beyond its rows.

The passages are rebuilt rather than copied. Copying vectors would be
faster, and was the first plan, but it means writing rows into the store by
hand with a new library on them - and every isolation guarantee Primer makes
is a filter over exactly those fields. Re-indexing runs the same path an
upload runs, which is the path that is already proven to scope them
correctly. The cost is that a duplicate is browsable at once and answerable
once its documents finish indexing, the same as any other upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from primer_control.models import IngestionJob, Library
from primer_control.repositories.documents import DocumentRepository
from primer_control.repositories.libraries import LibraryRepository
from primer_storage import StoredSource
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

#: Matches the column, and Control rejects anything longer. A copy of a
#: library whose name is already at the limit has to lose something, and
#: losing the end of the name beats failing the request.
MAX_NAME = 120


def copy_name(name: str, *, suffix: str = " (copy)") -> str:
    """A name for the copy, trimmed to fit rather than refused."""
    room = MAX_NAME - len(suffix)
    stem = name if len(name) <= room else name[:room].rstrip()
    return f"{stem}{suffix}"


@dataclass(frozen=True)
class Duplication:
    """The new library, and the indexing work it needs before it can answer."""

    library: Library
    jobs: tuple[IngestionJob, ...]


class LibraryDuplicator:
    """Copies a library the caller may read into a new one they own."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._libraries = LibraryRepository(session)
        self._documents = DocumentRepository(session)

    async def duplicate(
        self, source: Library, *, name: str, owner_user_id: UUID, where: ColumnElement[bool]
    ) -> Duplication:
        """Copy `source` into a new library owned by `owner_user_id`.

        The same authorization predicate that fetched the source library is
        applied again to its documents. Reading a library and reading what is
        in it are the same permission, and asking twice costs nothing.
        """
        records = await self._documents.find_all(library_id=source.id, where=where)
        library = await self._libraries.create(name=name, owner_user_id=owner_user_id)

        jobs: list[IngestionJob] = []
        for record in records:
            document = await self._documents.create_document(library_id=library.id)
            version = await self._documents.add_version(
                document,
                # The stored object is shared, not re-uploaded: it is
                # addressed by its content, and two libraries referencing one
                # blob is what that addressing is for.
                StoredSource(
                    sha256=record.version.source_sha256,
                    media_type=record.version.media_type,
                    byte_size=record.version.byte_size,
                    # True, and not a convenience: these bytes are already
                    # stored, which is exactly what deduplication means here.
                    deduplicated=True,
                ),
                filename=record.version.filename,
            )
            jobs.append(await self._documents.enqueue_job(version))

        return Duplication(library=library, jobs=tuple(jobs))

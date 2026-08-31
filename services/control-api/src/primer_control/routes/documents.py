"""Document upload, status, download, and deletion.

Documents inherit their library's authorization: an unreachable library and
an unreachable document return the same 404, so probing document ids reveals
nothing about libraries the caller cannot see.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from primer_contracts.documents import DocumentSummary, IngestionStatus
from primer_contracts.errors import ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.db import get_session
from primer_control.errors import ProblemError
from primer_control.identity import CurrentPrincipal
from primer_control.models import Document, Library
from primer_control.repositories.documents import DocumentRecord, DocumentRepository
from primer_control.repositories.libraries import LibraryRepository
from primer_control.services.library_access import LibraryAccess
from primer_control.source_store import QuotaExceeded, SourceStore, SourceStoreError

router = APIRouter(prefix="/api/v1/libraries/{library_id}/documents", tags=["documents"])

Session = Annotated[AsyncSession, Depends(get_session)]
access = LibraryAccess()

MAX_FILENAME_LENGTH = 255


def get_source_store(request: Request) -> SourceStore:
    store: SourceStore = request.app.state.source_store
    return store


Store = Annotated[SourceStore, Depends(get_source_store)]
Upload = Annotated[UploadFile, File(description="The source file to ingest")]


def not_found() -> ProblemError:
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title="Document not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No document with that identifier is available to you.",
    )


def as_problem(error: SourceStoreError) -> ProblemError:
    """Translate a rejected upload into its stable HTTP shape."""
    if isinstance(error, QuotaExceeded):
        return ProblemError(
            code=ErrorCode.QUOTA_EXCEEDED,
            title="Upload too large",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=error.message,
        )
    return ProblemError(
        code=ErrorCode.UNSUPPORTED_CONTENT,
        title="Unsupported file",
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=error.message,
    )


def safe_filename(raw: str | None) -> str:
    """Reduce a client-supplied name to a bare, storable filename.

    The name is echoed back in listings and download headers, so directory
    components and control characters are stripped here rather than trusted
    downstream.
    """
    candidate = PurePosixPath((raw or "").replace("\\", "/")).name
    candidate = "".join(character for character in candidate if character.isprintable()).strip()
    if not candidate or candidate in {".", ".."}:
        raise ProblemError(
            code=ErrorCode.VALIDATION_FAILED,
            title="Filename missing",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The upload must carry a filename.",
        )
    return candidate[:MAX_FILENAME_LENGTH]


def summarize(record: DocumentRecord) -> DocumentSummary:
    job = record.job
    return DocumentSummary(
        id=record.document.id,
        library_id=record.document.library_id,
        current_version_id=record.version.id,
        filename=record.version.filename,
        media_type=record.version.media_type,
        byte_size=record.version.byte_size,
        status=IngestionStatus(job.state) if job else IngestionStatus.QUEUED,
        status_detail=job.error_detail if job else None,
        created_at=record.document.created_at,
        updated_at=record.document.updated_at,
    )


async def _chunks(upload: UploadFile, size: int) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload.read(size)
        if not chunk:
            return
        yield chunk


async def require_library(library_id: UUID, principal_id: UUID, session: AsyncSession) -> Library:
    library = await LibraryRepository(session).get(
        library_id, where=access.manageable(principal_id)
    )
    if library is None:
        raise not_found()
    return library


async def store_version(
    *,
    document: Document | None,
    library_id: UUID,
    upload: UploadFile,
    store: SourceStore,
    session: AsyncSession,
) -> DocumentRecord:
    """Persist an upload as a new document, or as a replacement version.

    The bytes are made durable before any metadata is written, so a failed
    upload leaves no document row promising content that was never stored.
    """
    filename = safe_filename(upload.filename)
    try:
        stored = await store.put(_chunks(upload, store.chunk_bytes), filename=filename)
    except SourceStoreError as error:
        raise as_problem(error) from error

    repository = DocumentRepository(session)
    await repository.ensure_source(stored)
    if document is None:
        document = await repository.create_document(library_id=library_id)
    version = await repository.add_version(document, stored, filename=filename)
    job = await repository.enqueue_job(version)
    return DocumentRecord(document, version, job)


@router.get("", summary="List a library's documents")
async def list_documents(
    library_id: UUID, principal: CurrentPrincipal, session: Session
) -> list[DocumentSummary]:
    await require_library(library_id, principal.user_id, session)
    records = await DocumentRepository(session).find_all(
        library_id=library_id, where=access.readable(principal.user_id)
    )
    return [summarize(record) for record in records]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Upload a document")
async def upload_document(
    library_id: UUID,
    principal: CurrentPrincipal,
    session: Session,
    store: Store,
    file: Upload,
) -> DocumentSummary:
    await require_library(library_id, principal.user_id, session)
    record = await store_version(
        document=None, library_id=library_id, upload=file, store=store, session=session
    )
    return summarize(record)


@router.post(
    "/{document_id}/versions",
    status_code=status.HTTP_201_CREATED,
    summary="Replace a document with a new version",
)
async def replace_document(
    library_id: UUID,
    document_id: UUID,
    principal: CurrentPrincipal,
    session: Session,
    store: Store,
    file: Upload,
) -> DocumentSummary:
    """Add a version rather than overwriting one.

    Earlier versions stay readable so a citation pinned to a version keeps
    resolving to the text that was actually quoted.
    """
    await require_library(library_id, principal.user_id, session)
    repository = DocumentRepository(session)
    existing = await repository.get(
        document_id, library_id=library_id, where=access.manageable(principal.user_id)
    )
    if existing is None:
        raise not_found()
    record = await store_version(
        document=existing.document,
        library_id=library_id,
        upload=file,
        store=store,
        session=session,
    )
    return summarize(record)


@router.get("/{document_id}", summary="Read one document's status")
async def read_document(
    library_id: UUID, document_id: UUID, principal: CurrentPrincipal, session: Session
) -> DocumentSummary:
    await require_library(library_id, principal.user_id, session)
    record = await DocumentRepository(session).get(
        document_id, library_id=library_id, where=access.readable(principal.user_id)
    )
    if record is None:
        raise not_found()
    return summarize(record)


@router.get("/{document_id}/content", summary="Download the current version's bytes")
async def download_document(
    library_id: UUID,
    document_id: UUID,
    principal: CurrentPrincipal,
    session: Session,
    store: Store,
) -> StreamingResponse:
    await require_library(library_id, principal.user_id, session)
    record = await DocumentRepository(session).get(
        document_id, library_id=library_id, where=access.readable(principal.user_id)
    )
    if record is None:
        raise not_found()

    # RFC 5987 encoding, and never the storage key: how bytes are addressed
    # on the backend is not the caller's business.
    disposition = f"attachment; filename*=UTF-8''{quote(record.version.filename)}"
    return StreamingResponse(
        store.open_stream(record.version.source_sha256),
        media_type=record.version.media_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a document"
)
async def delete_document(
    library_id: UUID, document_id: UUID, principal: CurrentPrincipal, session: Session
) -> Response:
    await require_library(library_id, principal.user_id, session)
    repository = DocumentRepository(session)
    record = await repository.get(
        document_id, library_id=library_id, where=access.manageable(principal.user_id)
    )
    if record is None:
        raise not_found()
    await repository.soft_delete(record.document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

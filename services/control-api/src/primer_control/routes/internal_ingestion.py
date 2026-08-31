"""Job transitions for ingestion workers.

Cluster-internal: the edge proxy must not route `/internal` from outside.
Authorization here is a service credential, and no route takes a principal,
because a worker acts on a job rather than on behalf of a person. Every
route is safe to call twice - that is the point of the protocol, not a
side effect of it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from primer_contracts.errors import ErrorCode
from primer_contracts.ingestion import (
    ClaimResponse,
    StageClaim,
    StageCompletion,
    StageFailure,
    TransitionResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

from primer_control.config import Settings
from primer_control.db import get_session
from primer_control.errors import ProblemError
from primer_control.repositories.ingestion_jobs import IngestionJobRepository
from primer_control.security import require_service_credential

router = APIRouter(
    prefix="/internal/v1/ingestion",
    tags=["internal"],
    dependencies=[Depends(require_service_credential)],
    include_in_schema=False,
)

Session = Annotated[AsyncSession, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


Config = Annotated[Settings, Depends(get_settings)]


def unknown_job(job_id: UUID) -> ProblemError:
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title="Job not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No ingestion job {job_id} exists.",
    )


@router.post("/jobs/{job_id}/claim", summary="Take a stage of a job")
async def claim_stage(
    job_id: UUID, payload: StageClaim, session: Session, settings: Config
) -> ClaimResponse:
    """Return work, or the reason there is none.

    A refusal is a 200 with an outcome, not an error status: at-least-once
    delivery makes duplicate messages routine, and a worker that treated
    them as failures would retry work that is already done.
    """
    try:
        return await IngestionJobRepository(session).claim(
            job_id, payload.stage, lease_seconds=settings.job_lease_seconds
        )
    except LookupError as error:
        raise unknown_job(job_id) from error


@router.post("/jobs/{job_id}/heartbeat", summary="Extend a claim")
async def heartbeat(
    job_id: UUID, payload: StageCompletion, session: Session, settings: Config
) -> TransitionResult:
    try:
        return await IngestionJobRepository(session).heartbeat(
            job_id,
            payload.stage,
            payload.generation_id,
            lease_seconds=settings.job_lease_seconds,
        )
    except LookupError as error:
        raise unknown_job(job_id) from error


@router.post("/jobs/{job_id}/complete", summary="Advance a completed stage")
async def complete_stage(
    job_id: UUID, payload: StageCompletion, session: Session
) -> TransitionResult:
    try:
        return await IngestionJobRepository(session).complete(
            job_id, payload.stage, payload.generation_id
        )
    except LookupError as error:
        raise unknown_job(job_id) from error


@router.post("/jobs/{job_id}/fail", summary="Record a failed stage")
async def fail_stage(
    job_id: UUID, payload: StageFailure, session: Session, settings: Config
) -> TransitionResult:
    try:
        return await IngestionJobRepository(session).fail(
            job_id, payload, max_attempts=settings.max_job_attempts
        )
    except LookupError as error:
        raise unknown_job(job_id) from error

"""Stage orchestration.

The shape of every task is the same: claim, work, confirm the claim still
holds, complete, then publish the next stage. None of those steps trusts the
message it arrived on - the message carries only a job id, and Control
decides at each step whether this worker is still the one doing the work.

Handlers are looked up rather than called directly so the Docling and
Haystack pipelines can register their stages without this module importing
either of them.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from celery import Task
from primer_contracts.ingestion import (
    ClaimOutcome,
    FailureDisposition,
    JobClaim,
    StageFailure,
    StageName,
)

from primer_ingestion.celery_app import QUEUE_NAMES, TASK_NAMES, create_celery
from primer_ingestion.config import Settings
from primer_ingestion.control_client import ControlClient, JobTransitions
from primer_ingestion.errors import PermanentStageError, StageError

logger = logging.getLogger(__name__)

app = create_celery()

StageHandler = Callable[[JobClaim], None]
Publisher = Callable[[StageName, UUID], None]

#: What a worker publishes once a stage completes. Deletion ends the chain.
NEXT_STAGE: dict[StageName, StageName | None] = {
    StageName.PARSE: StageName.EMBED,
    StageName.EMBED: StageName.INDEX,
    StageName.INDEX: None,
    StageName.DELETE: None,
}

#: Populated by the parsing and retrieval pipelines as they land. A stage
#: with no handler fails permanently rather than silently succeeding, so a
#: half-deployed cluster cannot mark documents ready without indexing them.
HANDLERS: dict[StageName, StageHandler] = {}


def register_handler(stage: StageName, handler: StageHandler) -> None:
    HANDLERS[stage] = handler


def stage_unavailable(claim: JobClaim) -> None:
    raise PermanentStageError(
        "stage_unavailable",
        "This deployment has no worker able to run that stage.",
    )


@dataclass(frozen=True)
class StageOutcome:
    """What happened, and whether the caller should schedule a retry."""

    outcome: ClaimOutcome
    retry: bool = False
    error: StageError | None = None


def execute_stage(
    stage: StageName,
    job_id: UUID,
    *,
    control: JobTransitions,
    handler: StageHandler,
    publish: Publisher,
    retries_left: bool,
) -> StageOutcome:
    """Run one stage of one job.

    Every early return is a normal outcome of at-least-once delivery. The
    caller acknowledges the message in all of them: re-running a stage the
    job has already passed is exactly what this protocol exists to prevent.
    """
    response = control.claim(job_id, stage)
    if response.outcome is not ClaimOutcome.CLAIMED or response.claim is None:
        logger.info("job %s: nothing to do for %s (%s)", job_id, stage, response.outcome)
        return StageOutcome(response.outcome)

    claim = response.claim
    try:
        handler(claim)
    except StageError as error:
        return _report_failure(control, claim, error, retries_left=retries_left)
    except Exception:
        # The trace goes to the worker log, correlated by job id; only a
        # sanitized code reaches the row a user can read.
        logger.exception("job %s: %s stage raised", job_id, stage)
        return _report_failure(
            control,
            claim,
            StageError("stage_error", "The stage failed unexpectedly."),
            retries_left=retries_left,
        )

    # Cancellation and reindexing both happen while a stage is running, and
    # a stage can take minutes. Confirming the claim still holds before
    # completing is the second half of "check before and after the work".
    if not control.heartbeat(job_id, stage, claim.generation_id).applied:
        logger.info("job %s: claim on %s no longer holds; discarding result", job_id, stage)
        return StageOutcome(ClaimOutcome.SUPERSEDED)

    if control.complete(job_id, stage, claim.generation_id).applied:
        following = NEXT_STAGE[stage]
        if following is not None:
            publish(following, job_id)
    return StageOutcome(ClaimOutcome.CLAIMED)


def _report_failure(
    control: JobTransitions,
    claim: JobClaim,
    error: StageError,
    *,
    retries_left: bool,
) -> StageOutcome:
    """Tell Control how the stage failed, and whether it is worth trying again."""
    disposition = error.disposition
    if disposition is FailureDisposition.RETRY and not retries_left:
        disposition = FailureDisposition.FAILED

    control.fail(
        claim.job_id,
        StageFailure(
            stage=claim.stage,
            generation_id=claim.generation_id,
            code=error.code,
            detail=error.detail,
            disposition=disposition,
        ),
    )
    return StageOutcome(
        ClaimOutcome.CLAIMED,
        retry=disposition is FailureDisposition.RETRY,
        error=error,
    )


def backoff_seconds(retries: int, settings: Settings) -> float:
    """Exponential backoff with jitter, capped.

    Without jitter, a broker outage retried by every worker at once returns
    as a synchronized thundering herd the moment it recovers.
    """
    base = min(
        settings.retry_backoff_seconds * (2**retries),
        settings.retry_backoff_max_seconds,
    )
    # Not security-sensitive: this only spreads retries out in time.
    return base * (0.5 + secrets.randbelow(1000) / 2000)


def publish_stage(stage: StageName, job_id: UUID) -> None:
    """Chain the next stage explicitly, by job id and nothing else."""
    app.send_task(TASK_NAMES[stage], args=[str(job_id)], queue=QUEUE_NAMES[stage])


def run_task(task: Task, stage: StageName, job_id: str) -> str:
    settings: Settings = task.app.conf.primer_settings
    retries_left = task.request.retries < settings.max_retries

    with ControlClient(settings) as control:
        result = execute_stage(
            stage,
            UUID(job_id),
            control=control,
            handler=HANDLERS.get(stage, stage_unavailable),
            publish=publish_stage,
            retries_left=retries_left,
        )

    if result.retry:
        raise task.retry(
            exc=result.error,
            countdown=backoff_seconds(task.request.retries, settings),
            max_retries=settings.max_retries,
        )
    return result.outcome.value


@app.task(bind=True, name=TASK_NAMES[StageName.PARSE])
def parse_job(self: Task, job_id: str) -> str:
    return run_task(self, StageName.PARSE, job_id)


@app.task(bind=True, name=TASK_NAMES[StageName.EMBED])
def embed_job(self: Task, job_id: str) -> str:
    return run_task(self, StageName.EMBED, job_id)


@app.task(bind=True, name=TASK_NAMES[StageName.INDEX])
def index_job(self: Task, job_id: str) -> str:
    return run_task(self, StageName.INDEX, job_id)


@app.task(bind=True, name=TASK_NAMES[StageName.DELETE])
def delete_job(self: Task, job_id: str) -> str:
    return run_task(self, StageName.DELETE, job_id)

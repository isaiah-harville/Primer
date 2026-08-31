"""Contracts for the cluster-internal job transition protocol.

Workers own no ingestion state. Every transition goes through the Control
API, which is the only writer of job rows, so two workers handed the same
message cannot both decide they are the one doing the work.

Messages on the broker carry a job id and nothing else. Everything a worker
needs arrives in the claim response, so a message that sat in a queue across
a reindex cannot act on a stale copy of the document it was published with.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel
from primer_contracts.documents import IngestionStatus


class StageName(StrEnum):
    """The units of work a message can ask for."""

    PARSE = "parse"
    EMBED = "embed"
    INDEX = "index"
    DELETE = "delete"


class ClaimOutcome(StrEnum):
    """Why a worker may or may not proceed.

    Only `CLAIMED` authorizes work. The rest are ordinary, expected results
    of at-least-once delivery, not errors: a worker that sees them
    acknowledges the message and stops.
    """

    CLAIMED = "claimed"
    #: Another worker holds an unexpired lease on this stage.
    IN_PROGRESS = "in_progress"
    #: The job already moved past this stage; the message is a redelivery.
    ALREADY_COMPLETED = "already_completed"
    #: A newer generation superseded the one this message belongs to.
    SUPERSEDED = "superseded"
    #: The job was cancelled, or its document was deleted, while queued.
    CANCELLED = "cancelled"


class FailureDisposition(StrEnum):
    """What a failure means for the job, decided by the worker.

    The worker is the only party that knows whether a failure was transient,
    so it says so explicitly rather than leaving Control to infer it from an
    error code.
    """

    #: Try again, if the job has retries left.
    RETRY = "retry"
    #: Terminal: the stage failed and retrying cannot help.
    FAILED = "failed"
    #: Terminal: the document is not something Primer can ingest.
    UNSUPPORTED = "unsupported"


class JobClaim(WireModel):
    """Everything a worker needs, delivered at claim time.

    The scope fields are not conveniences: every chunk this job produces
    carries them, and retrieval filters on them, so a claim that could not
    name its library could not produce retrievable content.
    """

    job_id: UUID
    stage: StageName
    generation_id: UUID
    attempt: int = Field(ge=1)

    document_id: UUID
    document_version_id: UUID
    library_id: UUID
    owner_user_id: UUID

    source_sha256: str = Field(min_length=64, max_length=64)
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(ge=0)


class StageClaim(WireModel):
    """Ask to enter a stage. The job is named in the path, not the body."""

    stage: StageName


class ClaimResponse(WireModel):
    outcome: ClaimOutcome
    #: Present only when the outcome is `CLAIMED`.
    claim: JobClaim | None = None


class StageCompletion(WireModel):
    """Report that a claimed stage finished.

    The generation is echoed back so Control can refuse a completion for work
    that a reindex has already superseded.
    """

    stage: StageName
    generation_id: UUID


class StageFailure(WireModel):
    """Report that a claimed stage failed.

    `code` and `detail` are shown to users, so they must stay sanitized;
    exception traces belong in worker logs, correlated by job id.
    """

    stage: StageName
    generation_id: UUID
    code: str = Field(min_length=1, max_length=64)
    detail: str | None = Field(default=None, max_length=2000)
    #: A non-retryable failure goes straight to a terminal state instead of
    #: consuming the retry budget.
    disposition: FailureDisposition = FailureDisposition.RETRY


class TransitionResult(WireModel):
    """The outcome of a completion, failure, or heartbeat."""

    #: False when the transition did not apply, which is how a redelivered
    #: completion is distinguished from the first one.
    applied: bool
    status: IngestionStatus

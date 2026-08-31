"""The worker's only writer of job state.

Workers own no ingestion state and hold no database credentials. Every
transition is a request to Control, which decides whether it applies.
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

import httpx2
from primer_contracts.ingestion import (
    ClaimResponse,
    StageClaim,
    StageCompletion,
    StageFailure,
    StageName,
    TransitionResult,
)

from primer_ingestion.config import Settings

SERVICE_TOKEN_HEADER = "X-Primer-Service-Token"  # noqa: S105 - a header name, not a secret


class ControlClient:
    """Synchronous, because Celery tasks are."""

    def __init__(self, settings: Settings, client: httpx2.Client | None = None) -> None:
        token = settings.service_token
        self._client = client or httpx2.Client(
            base_url=settings.control_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
            headers=({SERVICE_TOKEN_HEADER: token.get_secret_value()} if token is not None else {}),
        )

    def __enter__(self) -> ControlClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: object) -> dict[str, object]:
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        body: dict[str, object] = response.json()
        return body

    def claim(self, job_id: UUID, stage: StageName) -> ClaimResponse:
        payload = StageClaim(stage=stage).model_dump(mode="json")
        return ClaimResponse.model_validate(
            self._post(f"/internal/v1/ingestion/jobs/{job_id}/claim", payload)
        )

    def heartbeat(self, job_id: UUID, stage: StageName, generation_id: UUID) -> TransitionResult:
        payload = StageCompletion(stage=stage, generation_id=generation_id).model_dump(mode="json")
        return TransitionResult.model_validate(
            self._post(f"/internal/v1/ingestion/jobs/{job_id}/heartbeat", payload)
        )

    def complete(self, job_id: UUID, stage: StageName, generation_id: UUID) -> TransitionResult:
        payload = StageCompletion(stage=stage, generation_id=generation_id).model_dump(mode="json")
        return TransitionResult.model_validate(
            self._post(f"/internal/v1/ingestion/jobs/{job_id}/complete", payload)
        )

    def fail(self, job_id: UUID, failure: StageFailure) -> TransitionResult:
        return TransitionResult.model_validate(
            self._post(
                f"/internal/v1/ingestion/jobs/{job_id}/fail", failure.model_dump(mode="json")
            )
        )

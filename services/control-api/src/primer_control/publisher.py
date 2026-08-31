"""Handing a job to the workers.

Publishing is deliberately not part of the upload transaction. A message
sent before the commit can outlive a rollback, and a worker would then claim
a job that does not exist. Routes publish through a background task, which
runs after the response - and therefore after the session dependency has
committed - so a message only ever names a job that is really there.

The reverse failure is possible and is the acceptable one: a crash between
commit and publish leaves a job queued in the database with no message. That
is visible, recoverable by re-enqueueing, and harms nothing in the meantime.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from primer_contracts.ingestion import StageName

logger = logging.getLogger(__name__)

#: Must match the worker's task and queue names, which are the wire protocol
#: between the two services.
TASK_NAMES: dict[StageName, str] = {
    StageName.PARSE: "ingestion.parse",
    StageName.EMBED: "ingestion.embed",
    StageName.INDEX: "ingestion.index",
    StageName.DELETE: "ingestion.delete",
}


class JobPublisher(Protocol):
    def publish(self, stage: StageName, job_id: UUID) -> None: ...


class NullPublisher:
    """Records the intent and does nothing.

    Used when no broker is configured, which is the default for a local
    checkout. Uploads still work and their jobs still exist; they simply stay
    queued until a worker deployment gives them somewhere to go.
    """

    def publish(self, stage: StageName, job_id: UUID) -> None:
        logger.info("no broker configured; job %s stays queued for %s", job_id, stage)


class CeleryJobPublisher:
    """Publishes onto the same broker topology the workers consume."""

    def __init__(self, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery("primer_control_publisher", broker=broker_url)
        self._app.conf.update(
            task_serializer="json",
            # Without confirms, a broker that drops the message says nothing,
            # and the job sits queued forever with no sign it was never sent.
            broker_transport_options={"confirm_publish": True},
        )

    def publish(self, stage: StageName, job_id: UUID) -> None:
        self._app.send_task(TASK_NAMES[stage], args=[str(job_id)], queue=TASK_NAMES[stage])


def build_publisher(broker_url: str | None) -> JobPublisher:
    return CeleryJobPublisher(broker_url) if broker_url else NullPublisher()

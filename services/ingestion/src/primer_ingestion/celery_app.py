"""Broker topology and failure policy.

Every setting here exists to make redelivery safe rather than rare. Messages
are acknowledged late, so a worker killed mid-stage causes redelivery instead
of silent loss, and the stage protocol in Control turns that redelivery into
a no-op.
"""

from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue
from primer_contracts.ingestion import StageName

from primer_ingestion.config import Settings

#: Task names are part of the wire protocol between Control and the workers,
#: so they are declared once here rather than derived from module paths.
TASK_NAMES: dict[StageName, str] = {
    StageName.PARSE: "ingestion.parse",
    StageName.EMBED: "ingestion.embed",
    StageName.INDEX: "ingestion.index",
    StageName.DELETE: "ingestion.delete",
}

#: A queue per task, named the same. Kept as its own mapping so a stage can
#: later be moved onto a shared queue without renaming its task.
QUEUE_NAMES: dict[StageName, str] = dict(TASK_NAMES)

DEAD_LETTER_EXCHANGE = "ingestion.dlx"
DEAD_LETTER_QUEUE = "ingestion.dead"
DEAD_LETTER_ROUTING_KEY = "dead"


def build_queues() -> tuple[Queue, ...]:
    """One queue per stage, each dead-lettering to a single holding queue.

    A message the broker gives up on lands somewhere an operator can inspect
    it. Dropping it instead would leave a document stuck in a non-terminal
    state with nothing to explain why.
    """
    exchange = Exchange("ingestion", type="direct")
    dead_exchange = Exchange(DEAD_LETTER_EXCHANGE, type="direct")
    stage_queues = [
        Queue(
            name,
            exchange,
            routing_key=name,
            queue_arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": DEAD_LETTER_ROUTING_KEY,
            },
        )
        for name in QUEUE_NAMES.values()
    ]
    return (
        *stage_queues,
        Queue(DEAD_LETTER_QUEUE, dead_exchange, routing_key=DEAD_LETTER_ROUTING_KEY),
    )


def create_celery(settings: Settings | None = None) -> Celery:
    """Build the Celery application from validated settings."""
    settings = settings or Settings()
    app = Celery("primer_ingestion", broker=settings.broker_url)
    app.conf.update(
        # Stages are long and side-effecting. Acknowledging late means a
        # crash redelivers rather than loses; the claim protocol makes the
        # redelivery harmless.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # One message at a time: a parse can hold hundreds of megabytes, and
        # prefetching would let one worker sit on jobs another could run.
        worker_prefetch_multiplier=1,
        broker_transport_options={"confirm_publish": True},
        task_time_limit=settings.task_time_limit_seconds,
        task_soft_time_limit=settings.task_soft_time_limit_seconds,
        task_queues=build_queues(),
        task_default_queue=QUEUE_NAMES[StageName.PARSE],
        task_default_exchange="ingestion",
        task_routes={TASK_NAMES[stage]: {"queue": queue} for stage, queue in QUEUE_NAMES.items()},
        # Results are not used: job state lives in Control, which is the only
        # place a user or another service reads it from.
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    app.conf.primer_settings = settings
    return app

"""Control's publisher and the ingestion worker must agree on the broker.

They are two separate services, deliberately not sharing a dependency on
each other, so the queue topology - names, exchange, and arguments - is
duplicated between `primer_control.publisher` and `primer_ingestion.celery_app`
rather than imported once. RabbitMQ treats a queue's arguments as part of
its identity: redeclaring an existing queue with different ones is refused
outright (406 PRECONDITION_FAILED), not merged or ignored. A publish that
hits this fails silently from a user's point of view - the upload that
triggered it already returned success - so the two definitions drifting out
of step is exactly the kind of bug this test exists to catch before a queue
in a real deployment does.
"""

from __future__ import annotations

from primer_control.publisher import TASK_NAMES as CONTROL_TASK_NAMES
from primer_control.publisher import CeleryJobPublisher
from primer_ingestion.celery_app import TASK_NAMES as WORKER_TASK_NAMES
from primer_ingestion.celery_app import create_celery


def test_task_names_agree() -> None:
    assert CONTROL_TASK_NAMES == WORKER_TASK_NAMES


def test_every_queue_the_publisher_declares_matches_the_worker() -> None:
    publisher = CeleryJobPublisher("amqp://guest:guest@localhost:5672//")
    worker = create_celery()

    published = {queue.name: queue for queue in publisher._app.conf.task_queues}
    consumed = {queue.name: queue for queue in worker.conf.task_queues}

    for name in CONTROL_TASK_NAMES.values():
        assert name in published, f"publisher does not declare {name!r}"
        assert name in consumed, f"worker does not declare {name!r}"

        theirs, ours = consumed[name], published[name]
        assert ours.exchange.name == theirs.exchange.name
        assert ours.exchange.type == theirs.exchange.type
        assert ours.routing_key == theirs.routing_key
        assert ours.queue_arguments == theirs.queue_arguments

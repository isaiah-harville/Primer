"""What the worker declares on the broker.

RabbitMQ 4.1 deprecated transient queues that are not exclusive, and 4.2
refuses to declare them. A worker that trips this cannot finish connecting:
it fails on its own mailbox, restarts, and hits the restart limiter within a
second, so the failure looks like a crash loop rather than a broker policy.

These are the queues Primer causes to exist, checked against that rule
directly rather than against the settings that happen to produce it.
"""

from __future__ import annotations

from celery.events.receiver import EventReceiver
from celery.utils.quorum_queues import detect_quorum_queues
from kombu import Queue
from primer_ingestion.celery_app import create_celery


def _declarable(queue: Queue) -> bool:
    """Whether a broker running RabbitMQ 4 will accept this declaration.

    A queue must survive a restart or belong to one connection. The
    combination that is refused is the one that promises neither.
    """
    return queue.durable or queue.exclusive


def _every_queue() -> dict[str, Queue]:
    """Every queue a worker declares, not only the ones Primer names.

    Celery declares a control mailbox and an event queue of its own, and
    those are the ones that were failing: testing only `task_queues` would
    have passed throughout.
    """
    app = create_celery()
    mailbox = app.control.mailbox
    queues = {
        "pidbox": mailbox.get_queue("worker@test"),
        "pidbox-reply": mailbox.get_reply_queue(),
        "events": EventReceiver(channel=None, app=app, node_id="test").queue,
    }
    for queue in app.conf.task_queues:
        queues[queue.name] = queue
    return queues


def test_every_declared_queue_is_durable_or_exclusive() -> None:
    offenders = {name: queue for name, queue in _every_queue().items() if not _declarable(queue)}
    assert offenders == {}, (
        f"transient non-exclusive queues are refused by RabbitMQ 4: {sorted(offenders)}"
    )


def test_the_worker_does_not_ask_for_channel_wide_prefetch() -> None:
    """RabbitMQ has deprecated global QoS and logs an error for every use.

    Celery decides this from the queues rather than from a setting: it stops
    asking once it sees a quorum queue. So the property worth testing is the
    decision itself, which is what would silently revert if the queue type
    were changed back.
    """
    app = create_celery()

    using_quorum, _ = detect_quorum_queues(app, "amqp")

    assert using_quorum, "Celery only disables global QoS when it sees a quorum queue"
    assert app.conf.worker_detect_quorum_queues, "detection is what acts on the queue type"


def test_the_work_queues_survive_a_broker_restart() -> None:
    """Stage queues are durable, which is a stronger claim than declarable.

    A queued document must still be queued after the broker restarts. The
    control and event queues are deliberately the opposite: a dead worker's
    mailbox should not outlive it.
    """
    app = create_celery()
    for queue in app.conf.task_queues:
        assert queue.durable, f"{queue.name} would lose queued work on a broker restart"
        assert not queue.exclusive, f"{queue.name} must be consumable by any worker"
        arguments = queue.queue_arguments or {}
        assert arguments.get("x-queue-type") == "quorum", (
            f"{queue.name} should be a quorum queue: ingestion work must outlive the broker"
        )

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

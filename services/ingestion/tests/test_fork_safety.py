"""Storage clients must belong to the process that uses them.

The Celery prefork pool forks after the worker module is imported, so
anything the import built lives in the parent and is inherited by every
child. For an fsspec filesystem backed by object storage that is fatal: it
is an async filesystem, it records the pid and event loop it was created on,
and it refuses to run for any other process - `RuntimeError: This class is
not fork-safe`, raised before a single byte is transferred.

The parse stage reports that as a failed document. A deployment hits it on
the first upload and every one after, so nothing it ingests is ever
readable, and the only symptom is a library full of documents marked failed.

These tests fork for real and use the store object the child inherited, not
a freshly resolved one. Both details matter: mocking the pool would test the
mock, and re-resolving the URL in the child hides the bug, because what the
pool hands a child is the parent's object rather than its address.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

import fsspec
import pytest
from celery.signals import worker_process_init
from primer_contracts.ingestion import StageName
from primer_ingestion import worker
from primer_ingestion.tasks import HANDLERS
from primer_storage import SourceStore

#: Object storage, not a local directory. `file://` yields a synchronous
#: filesystem that survives a fork happily, so a test written against one
#: would pass with the bug fully present. No server is contacted: the fork
#: check fires before any request is made, which is why these tests need
#: neither credentials nor a bucket.
OBJECT_STORE_URL = "s3://primer-test-sources"

#: A hash of the right shape that nothing will ever have stored. Reaching a
#: "not found" from the child is the success condition: it means the call
#: got past the fork check and out to the store.
ABSENT_SHA256 = "0" * 64

#: Forking is the whole subject, so the pool method is pinned rather than
#: left to the platform default - macOS spawns, which would quietly build
#: fresh objects in the child and prove nothing.
FORK = multiprocessing.get_context("fork")

#: Forking a multi-threaded process is only dependable on the platform the
#: workers actually run on. macOS kills the child inside its own runtime
#: before it reaches anything Primer wrote, which says nothing about the
#: behaviour under test.
runs_where_the_workers_do = pytest.mark.skipif(
    not hasattr(os, "fork") or sys.platform == "darwin",
    reason="the prefork pool runs on Linux; on macOS the child dies in the platform runtime",
)


def built_in_the_parent() -> SourceStore:
    """A source store built here, standing in for the one the import builds."""
    return SourceStore(OBJECT_STORE_URL, max_bytes=1 << 20)


def use_inherited(store: SourceStore, results: multiprocessing.Queue[str]) -> None:
    """Read through the store this child inherited, and report what happened."""
    try:
        store.download(ABSENT_SHA256, Path(os.devnull))
    except Exception as error:  # noqa: BLE001 - the failure mode is what is under test
        results.put(f"{type(error).__name__}: {error}")
    else:
        results.put("no error")


def rebuild_then_use(inherited: SourceStore, results: multiprocessing.Queue[str]) -> None:
    """The same, after the child has done what the signal handler does.

    The inherited store is taken and dropped on purpose: rebuilding is what
    the child is supposed to do with it, and holding on to it would be the
    bug this file exists to keep out.
    """
    del inherited
    worker.rebuild_after_fork()
    use_inherited(built_in_the_parent(), results)


def in_child(target, store: SourceStore) -> str:
    results: multiprocessing.Queue[str] = FORK.Queue()
    process = FORK.Process(target=target, args=(store, results))
    process.start()
    process.join(timeout=60)
    assert not process.is_alive(), "the forked child hung"
    assert process.exitcode == 0, f"the child died with {process.exitcode}"
    return results.get(timeout=10)


@runs_where_the_workers_do
def test_a_store_built_before_the_fork_is_unusable_in_the_child() -> None:
    """The bug itself, so the rest of this file is known to be testing something.

    If this ever stops holding - fsspec learning to rebuild itself across a
    fork, say - the fix below becomes unnecessary rather than wrong, and
    this is the test that should say so.
    """
    fsspec.AbstractFileSystem.clear_instance_cache()
    outcome = in_child(use_inherited, built_in_the_parent())

    assert "not fork-safe" in outcome, outcome


@runs_where_the_workers_do
def test_rebuilding_after_the_fork_gives_the_child_a_working_store() -> None:
    """The fix: clearing the inherited cache is what makes the rebuild real.

    Rebuilding alone would not be enough. fsspec keys its instance cache on
    the constructor arguments, and that cache crosses the fork too, so a
    child asking for the same URL is handed the parent's object straight
    back.

    Success is a plain missing object. Anything the store can say about the
    bytes it was asked for means the call reached the store, which is all
    that was ever in doubt.
    """
    fsspec.AbstractFileSystem.clear_instance_cache()
    outcome = in_child(rebuild_then_use, built_in_the_parent())

    assert "not fork-safe" not in outcome, outcome


def test_every_stage_is_re_registered_after_a_fork() -> None:
    """A rebuild that left a stage behind would fail those documents instead."""
    worker.rebuild_after_fork()
    assert set(HANDLERS) == set(StageName)


def test_the_rebuild_runs_when_a_pool_child_starts() -> None:
    """Connected to the signal, not merely defined.

    The function could be perfect and never called; the wiring is what was
    missing, and it is invisible to any test that calls it directly. So the
    signal is raised the way Celery raises it in a new pool child, and the
    stages are checked for having genuinely been rebuilt - a fresh object,
    not the one the parent left behind.
    """
    worker.register_stages()
    inherited = HANDLERS[StageName.PARSE]

    worker_process_init.send(sender=None)

    assert HANDLERS[StageName.PARSE] is not inherited

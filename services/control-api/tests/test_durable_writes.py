"""A 2xx means the write is readable, not that it is about to be.

FastAPI closes a `yield` dependency's teardown after the response has been
sent, so a session that commits there commits after the client already holds
its 201. The client is then entitled to read its own write back and not find
it, which is precisely what a UI does when it refreshes a list after an
upload.

That is not a theoretical window. Measured against a running stack, an
uploaded document was missing from its library's listing for about three
seconds after the upload returned 201 - long enough that every refresh the
page performed on its own came back without it, and only a manual reload
showed it. The same shape explains a deleted conversation still listed and a
newly created library missing from the sidebar.

What is pinned here is the ordering: the commit happens at the endpoint
boundary rather than in the teardown. The teardown is the part that runs
after the response, so a commit that precedes it is a commit the client's
next request can see.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from primer_service.durable import SESSION_STATE, DurableRoute


class Recording:
    """Stands in for a session, recording when it was committed."""

    def __init__(self, events: list[str], *, wrote: bool) -> None:
        self.events = events
        self.new: set[Any] = {"a row"} if wrote else set()
        self.dirty: set[Any] = set()
        self.deleted: set[Any] = set()

    def in_transaction(self) -> bool:
        return True

    async def commit(self) -> None:
        self.events.append("commit")


def stack(*, wrote: bool) -> tuple[TestClient, list[str]]:
    """An app shaped like the real one: DurableRoute over a yield session."""
    events: list[str] = []
    session = Recording(events, wrote=wrote)

    async def get_session(request: Request) -> Any:
        setattr(request.state, SESSION_STATE, session)
        yield session
        # Where the real dependency commits, and the whole problem: FastAPI
        # runs this after the response has gone out.
        events.append("teardown")

    router = APIRouter(route_class=DurableRoute)

    @router.post("/things", status_code=201)
    async def create(_: Any = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        events.append("endpoint")
        return {"created": "yes"}

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), events


def test_the_write_is_committed_before_the_teardown() -> None:
    """The regression. The teardown is the part that runs after the response,
    so committing there is committing after the client has been told 201."""
    caller, events = stack(wrote=True)

    assert caller.post("/things").status_code == 201
    assert events == ["endpoint", "commit", "teardown"]


def test_a_flushed_write_is_still_committed() -> None:
    """The subtle one, and it cost roughly one upload in ten.

    Skipping sessions with nothing pending looks like an obvious saving and
    is wrong: the repositories flush to obtain identifiers, and a flushed
    object is no longer `new` or `dirty` - it is persistent, and uncommitted.
    A session that looks clean can be holding the entire write.
    """
    caller, events = stack(wrote=False)

    caller.post("/things")

    assert events == ["endpoint", "commit", "teardown"]


@pytest.mark.parametrize("field", ["new", "dirty", "deleted"])
def test_every_kind_of_pending_change_counts(field: str) -> None:
    """A delete is a write too. A deleted conversation still listed in the
    sidebar was one of the symptoms, and it dirties `deleted`, not `new`."""
    events: list[str] = []
    session = Recording(events, wrote=False)
    setattr(session, field, {"something"})

    async def get_session(request: Request) -> Any:
        setattr(request.state, SESSION_STATE, session)
        yield session
        events.append("teardown")

    router = APIRouter(route_class=DurableRoute)

    @router.post("/things", status_code=201)
    async def create(_: Any = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        events.append("endpoint")
        return {"created": "yes"}

    app = FastAPI()
    app.include_router(router)
    TestClient(app).post("/things")

    assert events == ["endpoint", "commit", "teardown"]

"""Committing before the client is told the write succeeded.

FastAPI closes a `yield` dependency's teardown *after* the response has been
sent, so a session that commits there commits after the client already has
its 201. The client is then entitled to read its own write back and not find
it - which is exactly what a UI does when it refreshes a list after an
upload, and exactly why documents, deleted conversations and newly created
libraries all appeared to need a manual refresh.

The gap is small and entirely real: measured against a running stack, a
document was absent from its library's listing for about three seconds after
the upload returned 201.

Done as a route class rather than an `await session.commit()` at the end of
each write handler. There is no way to forget this one, and the failure mode
of forgetting the other kind is a route that silently goes back to being
eventually consistent - which is the bug, and it took a while to find once.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

#: Where `get_session` leaves the session so this can reach it. A request
#: that never asked for one simply has nothing here.
SESSION_STATE = "primer_session"


class DurableRoute(APIRoute):
    """Commits the request's session before its response goes out.

    The endpoint has returned by the time this runs, but the exit stack
    holding the session is still open and the response has not been
    transmitted - which is the one moment where committing changes the
    guarantee the status code makes.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def durable(request: Request) -> Response:
            response = await handler(request)
            session = getattr(request.state, SESSION_STATE, None)
            # An open transaction is the whole condition. It is tempting to
            # skip reads by testing `session.new or dirty or deleted` first,
            # and that is wrong: the repositories flush to obtain identifiers,
            # and a flushed object is no longer new or dirty - it is
            # persistent, and uncommitted. Measured against a running stack
            # that heuristic dropped roughly one upload in ten back into
            # exactly the behaviour this exists to remove.
            #
            # Committing a transaction that only read is close to free and is
            # what the session's own teardown would have done anyway.
            if session is not None and session.in_transaction():
                await session.commit()
            return response

        return durable

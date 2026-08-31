"""Request correlation.

Every response carries a request ID so a sanitized user-facing error can be
matched to the operational detail in logs without leaking that detail.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CallNext = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adopt the edge's request ID when present, otherwise mint one."""

    def __init__(self, app: object, header_name: str) -> None:
        super().__init__(app)  # ty: ignore[invalid-argument-type]
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        request_id = request.headers.get(self.header_name) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self.header_name] = request_id
        return response

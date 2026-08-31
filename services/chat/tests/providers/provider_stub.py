"""A minimal stand-in for an OpenAI-compatible server.

A real socket rather than a patched client: the diagnostics exist to tell an
operator whether an endpoint is reachable, refusing, or serving something
else, and a mocked HTTP client cannot distinguish those - it would assert
that the code calls a function, not that it survives a real connection.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType


class StubProvider:
    """Serves `/v1/models`, counting requests, until the context exits."""

    def __init__(self, models: list[str] | None = None, status: int = 200) -> None:
        self._models = models or []
        self._status = status
        self.requests = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    async def __aenter__(self) -> StubProvider:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                stub.requests += 1
                body = json.dumps({"data": [{"id": name} for name in stub._models]}).encode()
                self.send_response(stub._status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                """Silence the default stderr access log."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

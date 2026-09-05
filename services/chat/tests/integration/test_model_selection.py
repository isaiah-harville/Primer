"""Choosing which model answers.

A deployment offers everything its own chat endpoint currently serves.
Primer keeps no list of its own to curate it against, so the dropdown and
the endpoint always agree - a model added or removed there shows up here
without redeploying Primer to match.
"""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType

import pytest
from chat_support import ChatUser, FakeGenerator
from httpx2 import AsyncClient
from primer_chat.config import Settings

MODELS = ("primary-model", "second-model")


class _StubEndpoint:
    """A minimal stand-in for an OpenAI-compatible server's `/models`.

    Not the same helper `tests/providers` uses for diagnostics: importing
    across sibling test directories only resolves at pytest's runtime, not
    under `ty`'s static check, so this stays local to the suite that needs
    it rather than fighting that.
    """

    def __init__(self, models: list[str]) -> None:
        self._models = models
        self.requests = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    async def __aenter__(self) -> _StubEndpoint:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                stub.requests += 1
                body = json.dumps({"data": [{"id": name} for name in stub._models]}).encode()
                self.send_response(200)
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


@pytest.fixture
async def provider() -> AsyncIterator[_StubEndpoint]:
    async with _StubEndpoint(models=list(MODELS)) as stub:
        yield stub


@pytest.fixture
def settings(provider: _StubEndpoint) -> Settings:
    """A deployment whose chat endpoint serves two models."""
    return Settings(
        auth_mode="oidc",
        chat_model=MODELS[0],
        chat_base_url=f"http://127.0.0.1:{provider.port}",
    )


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


async def test_the_endpoints_models_are_listed_with_the_default_first(
    user: ChatUser, provider: _StubEndpoint
) -> None:
    body = (await user.get("/api/v1/models")).json()

    assert [entry["id"] for entry in body["models"]] == list(MODELS)
    assert [entry["default"] for entry in body["models"]] == [True, False]
    assert provider.requests > 0


async def test_a_request_with_no_preference_uses_the_default(
    user: ChatUser, generator: FakeGenerator
) -> None:
    events = await user.ask(None, "What is a primer?")

    assert generator.models == [MODELS[0]]
    assert events[-1]["message"]["provider_model"] == MODELS[0]


async def test_a_chosen_model_reaches_the_provider_and_is_recorded(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """Recorded, because an answer's provenance includes what wrote it."""
    events = await user.ask(None, "What is a primer?", model=MODELS[1])

    assert generator.models == [MODELS[1]]
    assert events[-1]["message"]["provider_model"] == MODELS[1]


async def test_a_name_the_endpoint_no_longer_lists_is_still_forwarded(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """Primer is not the boundary here - the endpoint is.

    A name that stopped being served between listing and asking is the
    provider's failure to report, handled as any other model error is,
    rather than a second gate Primer keeps of its own.
    """
    events = await user.ask(None, "Anything", model="a-model-nobody-listed")

    assert generator.models == ["a-model-nobody-listed"]
    assert events[-1]["message"]["provider_model"] == "a-model-nobody-listed"


class TestWhenTheEndpointCannotBeReached:
    """Nothing is offered, and the reason travels with the empty list.

    This used to assert the opposite - that the configured default was
    offered anyway - which is what made an endpoint that was down look
    exactly like one that was up, right until somebody asked a question.
    """

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            auth_mode="oidc",
            chat_model="only-model",
            # Nothing listens here; the connection is refused immediately.
            chat_base_url="http://127.0.0.1:1",
        )

    async def test_no_model_is_offered(self, user: ChatUser) -> None:
        body = (await user.get("/api/v1/models")).json()

        assert body["models"] == []
        assert body["endpoint_reachable"] is False

    async def test_the_reason_names_the_endpoint(self, user: ChatUser) -> None:
        """Whoever reads this is usually whoever has to go and fix it."""
        body = (await user.get("/api/v1/models")).json()

        assert "127.0.0.1:1" in body["detail"]


class TestWithNoChatEndpointConfigured:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(auth_mode="oidc", chat_model="only-model")

    async def test_no_model_is_offered(self, user: ChatUser) -> None:
        """A deployment with no endpoint configured can answer nothing."""
        body = (await user.get("/api/v1/models")).json()

        assert body["models"] == []
        assert body["endpoint_reachable"] is False
        assert body["detail"]


async def test_the_provider_is_recorded_beside_the_model(user: ChatUser) -> None:
    """So a reopened conversation can select the same model again.

    A model name does not identify an endpoint - two providers serving
    `llama3.1:8b` is the ordinary case - so recording the name alone left a
    conversation able to say what answered it without being able to go back
    to it. The follow-up then went to the deployment's default, silently
    changing models mid-thread.
    """
    events = await user.ask(None, "Which model is this?")
    message = events[-1]["message"]

    assert "provider_id" in message

    stored = (await user.get(f"/api/v1/conversations/{message['conversation_id']}/messages")).json()
    answer = next(item for item in stored if item["role"] == "assistant")
    assert answer["provider_id"] == message["provider_id"]
    assert answer["provider_model"] == message["provider_model"]

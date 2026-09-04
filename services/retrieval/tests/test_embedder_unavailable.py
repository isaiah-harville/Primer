"""An unreachable embedding endpoint, reported as itself.

The embedder is a separate process that has to be running and reachable, so
this is the single most likely thing to be wrong on a self-hosted install.
It used to surface as an unhandled exception and a bare 500 with a stack
trace, which Chat then reported to the reader as an answer that stopped -
sending whoever read it to look at the model, which was fine.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from primer_retrieval.app import create_app
from primer_retrieval.config import Settings

#: These routes are cluster-internal and take a service credential; the
#: value is only ever compared against itself.
SERVICE_TOKEN = "test-service-token"  # noqa: S105


class UnreachableEmbedder:
    """Fails the way an endpoint that is not there fails."""

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Connection error.")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = create_app(
        Settings(
            embedding_base_url="http://nothing-here:8080/v1",
            embedding_dimensions=384,
            internal_api_token=SERVICE_TOKEN,
        ),
        store=object(),  # ty: ignore[invalid-argument-type]
        document_embedder=object(),  # ty: ignore[invalid-argument-type]
        text_embedder=UnreachableEmbedder(),  # ty: ignore[invalid-argument-type]
        retriever=object(),
    )
    return TestClient(app, raise_server_exceptions=False)


def search(client: TestClient) -> Any:
    return client.post(
        "/internal/v1/search",
        headers={"X-Primer-Service-Token": SERVICE_TOKEN},
        json={
            "principal": {
                "subject": "someone",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "groups": [],
            },
            "library_id": "22222222-2222-4222-8222-222222222222",
            "generation_ids": ["33333333-3333-4333-8333-333333333333"],
            "query": "anything",
            "limit": 6,
        },
    )


def test_it_is_a_dependency_failure_rather_than_a_crash(client: TestClient) -> None:
    """503, not 500. Nothing is wrong with the request."""
    response = search(client)

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"


def test_the_reason_names_the_embedder(client: TestClient) -> None:
    """So the reader looks at the embedder rather than at the model."""
    detail = search(client).json()["detail"]

    assert "embedding" in detail.lower()


def test_no_stack_trace_reaches_the_caller(client: TestClient) -> None:
    """The trace belongs in the log, correlated by request id."""
    body = str(search(client).json())

    assert "Traceback" not in body
    assert "ConnectionError" not in body

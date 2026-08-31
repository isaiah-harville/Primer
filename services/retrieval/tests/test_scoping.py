"""Scope enforcement, proven before any store is reached.

The store and retriever here refuse to be used at all. A request that got
past validation would fail loudly rather than quietly returning something,
so these tests cannot pass by accident.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from haystack import Document
from primer_contracts.identity import Principal
from primer_retrieval.app import create_app
from primer_retrieval.config import Settings
from pydantic import ValidationError

SERVICE_TOKEN = "retrieval-test-token"  # noqa: S105 - a fixture value, not a real credential
LIBRARY_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "library"))
GENERATION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "generation"))
VERSION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "version"))


class Tripwire:
    """Fails on contact. Reaching it at all is the bug under test."""

    def __getattr__(self, name: str) -> Any:
        def explode(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(f"the store was reached: {name}")

        return explode


class RecordingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, text: str) -> dict[str, Any]:
        self.calls += 1
        return {"embedding": [0.0] * 8}


@pytest.fixture
def embedder() -> RecordingEmbedder:
    return RecordingEmbedder()


@pytest.fixture
def client(embedder: RecordingEmbedder) -> TestClient:
    app = create_app(
        Settings(internal_api_token=SERVICE_TOKEN, embedding_dimensions=8),
        store=Tripwire(),  # ty: ignore[invalid-argument-type]
        document_embedder=Tripwire(),  # ty: ignore[invalid-argument-type]
        text_embedder=embedder,
        retriever=Tripwire(),
    )
    return TestClient(app)


def principal() -> dict[str, Any]:
    return Principal(
        subject="scoped-user", user_id=uuid.uuid5(uuid.NAMESPACE_URL, "scoped-user")
    ).model_dump(mode="json")


def search_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "principal": principal(),
        "library_id": LIBRARY_ID,
        "generation_ids": [GENERATION_ID],
        "query": "attention",
        "limit": 5,
    }
    body.update(overrides)
    return body


def post(client: TestClient, path: str, body: dict[str, Any], *, token: str | None = SERVICE_TOKEN):
    headers = {"X-Primer-Service-Token": token} if token is not None else {}
    return client.post(f"/internal/v1{path}", json=body, headers=headers)


@pytest.mark.parametrize("missing", ["library_id", "generation_ids", "principal", "query"])
def test_an_unscoped_search_is_refused_before_the_store(
    client: TestClient, embedder: RecordingEmbedder, missing: str
) -> None:
    """Omission is a validation error, never an empty filter."""
    body = search_body()
    del body[missing]

    response = post(client, "/search", body)

    assert response.status_code == 422
    assert embedder.calls == 0


def test_an_empty_generation_list_is_refused(client: TestClient) -> None:
    """An empty `in` filter matches nothing on one backend and everything on another."""
    assert post(client, "/search", search_body(generation_ids=[])).status_code == 422


def test_a_search_cannot_ask_for_an_unbounded_page(client: TestClient) -> None:
    assert post(client, "/search", search_body(limit=5000)).status_code == 422
    assert post(client, "/search", search_body(limit=0)).status_code == 422


def test_indexing_nothing_is_refused(client: TestClient) -> None:
    """An empty index call is a bug in the caller, not a no-op worth accepting."""
    response = post(
        client,
        "/index",
        {
            "principal": principal(),
            "library_id": LIBRARY_ID,
            "document_version_id": VERSION_ID,
            "generation_id": GENERATION_ID,
            "chunks": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_every_route_requires_the_service_credential(client: TestClient, token: str | None) -> None:
    for path, body in [
        ("/search", search_body()),
        (
            "/verify",
            {
                "principal": principal(),
                "library_id": LIBRARY_ID,
                "document_version_id": VERSION_ID,
                "generation_id": GENERATION_ID,
            },
        ),
        (
            "/delete",
            {
                "principal": principal(),
                "library_id": LIBRARY_ID,
                "document_version_id": VERSION_ID,
                "generation_id": GENERATION_ID,
            },
        ),
    ]:
        response = post(client, path, body, token=token)
        assert response.status_code == 401, path
        assert response.json()["code"] == "identity_invalid"


def test_an_unconfigured_credential_denies_everything() -> None:
    """A missing environment variable must not mean an open path to every library."""
    app = create_app(
        Settings(internal_api_token=None, embedding_dimensions=8),
        store=Tripwire(),  # ty: ignore[invalid-argument-type]
        document_embedder=Tripwire(),  # ty: ignore[invalid-argument-type]
        text_embedder=Tripwire(),  # ty: ignore[invalid-argument-type]
        retriever=Tripwire(),
    )
    response = TestClient(app).post(
        "/internal/v1/search",
        json=search_body(),
        headers={"X-Primer-Service-Token": ""},
    )
    assert response.status_code == 401


def test_the_search_contract_itself_requires_a_scope() -> None:
    """Held at the contract, so every future caller inherits it."""
    from primer_contracts.indexing import SearchRequest

    with pytest.raises(ValidationError):
        SearchRequest(  # ty: ignore[missing-argument]
            principal=Principal(subject="x", user_id=uuid.uuid4()),
            query="anything",
        )


def test_a_stored_document_keeps_its_verbatim_text() -> None:
    """What is embedded and what is quoted are different strings by design."""
    from primer_contracts.chunks import DocumentChunk
    from primer_retrieval.pipelines import to_documents

    chunk = DocumentChunk(
        chunk_id=uuid.uuid4(),
        ordinal=0,
        library_id=uuid.UUID(LIBRARY_ID),
        document_id=uuid.uuid4(),
        document_version_id=uuid.UUID(VERSION_ID),
        owner_user_id=uuid.uuid4(),
        generation_id=uuid.UUID(GENERATION_ID),
        content="The corpus was small.",
        embedding_text="Findings\nThe corpus was small.",
        filename="paper.pdf",
    )

    class Echo:
        def run(self, documents: list[Document]) -> dict[str, Any]:
            assert documents[0].content == "Findings\nThe corpus was small."
            return {
                "documents": [
                    Document(id=documents[0].id, content=documents[0].content, embedding=[0.5] * 8)
                ]
            }

    stored = to_documents((chunk,), Echo())

    assert stored[0].content == "The corpus was small."
    assert stored[0].embedding == [0.5] * 8

"""What a stage reports when Retrieval will not or cannot answer.

The point of these is the message a person ends up reading. A worker that
let an HTTP error escape reported it through the catch-all in `tasks`, which
is deliberately sanitized - so an embedding endpoint that was refusing
connections arrived on a user's screen as "The stage failed unexpectedly",
the same words as a genuine bug in Primer. Nothing in that sentence tells
an operator which of the two it was, or where to look.

They also fix the retry decision, which is the other half: a document
failing because something is temporarily down should come back on its own,
and a document Retrieval refuses on its merits should not be retried until
the budget runs out before anyone is told.
"""

from __future__ import annotations

import uuid

import httpx2
import pytest
from primer_contracts.chunks import DocumentChunk
from primer_contracts.indexing import IndexRequest
from primer_contracts.ingestion import FailureDisposition
from primer_ingestion.config import Settings
from primer_ingestion.errors import StageError
from primer_ingestion.retrieval_client import RetrievalClient, worker_principal

OWNER = uuid.UUID("11111111-1111-5111-8111-111111111111")
LIBRARY = uuid.UUID("22222222-2222-5222-8222-222222222222")
VERSION = uuid.UUID("33333333-3333-5333-8333-333333333333")
GENERATION = uuid.UUID("44444444-4444-5444-8444-444444444444")


def a_request() -> IndexRequest:
    return IndexRequest(
        principal=worker_principal(OWNER),
        library_id=LIBRARY,
        document_version_id=VERSION,
        generation_id=GENERATION,
        chunks=(
            DocumentChunk(
                chunk_id=uuid.uuid5(GENERATION, "0"),
                owner_user_id=OWNER,
                library_id=LIBRARY,
                document_id=uuid.uuid5(VERSION, "document"),
                document_version_id=VERSION,
                generation_id=GENERATION,
                ordinal=0,
                content="The budget rose.",
                embedding_text="Finances. The budget rose.",
                filename="report.pdf",
            ),
        ),
    )


def client_answering(handler: object) -> RetrievalClient:
    """A client wired to a transport that answers however a test wants."""
    return RetrievalClient(
        Settings(),
        client=httpx2.Client(
            base_url="http://retrieval.invalid",
            transport=httpx2.MockTransport(handler),  # ty: ignore[invalid-argument-type]
        ),
    )


def answering(status_code: int, body: dict[str, object] | None = None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code, json=body if body is not None else {})

    return handler


def test_an_unavailable_dependency_is_named_and_retried() -> None:
    """The words Retrieval chose reach the person who has to act on them."""
    index = client_answering(
        answering(
            503,
            {
                "code": "dependency_unavailable",
                "detail": "The embedding endpoint could not be reached, "
                "so this document cannot be indexed.",
            },
        )
    )

    with pytest.raises(StageError) as raised:
        index.index(a_request())

    assert raised.value.code == "retrieval_unavailable"
    assert raised.value.detail is not None
    assert "embedding endpoint" in raised.value.detail
    assert raised.value.disposition is FailureDisposition.RETRY


def test_a_refused_request_is_not_retried() -> None:
    """Retrieval will refuse it identically every time.

    Retrying only delays the moment someone is told, and spends the budget
    that a genuinely transient failure needs.
    """
    index = client_answering(answering(422, {"code": "invalid_request", "detail": "Bad scope."}))

    with pytest.raises(StageError) as raised:
        index.index(a_request())

    assert raised.value.code == "retrieval_rejected"
    assert raised.value.disposition is FailureDisposition.FAILED


def test_nothing_answering_at_all_is_retried_and_says_so() -> None:
    """A refused connection is the shape of a service that is restarting."""

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("Connection refused.")

    index = client_answering(refuse)

    with pytest.raises(StageError) as raised:
        index.index(a_request())

    assert raised.value.code == "retrieval_unavailable"
    assert raised.value.detail == "Retrieval could not be reached."
    assert raised.value.disposition is FailureDisposition.RETRY


def test_a_failure_that_is_not_a_problem_document_still_says_something() -> None:
    """A proxy's own error page is not Primer's, and reaches here as HTML.

    The status is then all there is to report, and reporting it is still
    better than the catch-all: it says Retrieval was reached and answered.
    """
    index = client_answering(lambda request: httpx2.Response(502, text="<html>Bad Gateway</html>"))

    with pytest.raises(StageError) as raised:
        index.index(a_request())

    assert raised.value.code == "retrieval_unavailable"
    assert raised.value.detail == "Retrieval answered 502."

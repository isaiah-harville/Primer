"""Wire-contract behavior that every Primer service depends on."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from primer_contracts.chat import ChatRequest, Citation
from primer_contracts.documents import DocumentSummary, IngestionStatus
from primer_contracts.errors import ErrorCode, ProblemDetail
from primer_contracts.identity import Principal
from primer_contracts.libraries import LibrarySummary
from primer_contracts.retrieval import RetrievalRequest, RetrievedChunk, SourceLocator
from pydantic import ValidationError


def make_principal() -> Principal:
    return Principal(subject="oidc-user", user_id=uuid4(), groups=("researchers",))


def test_retrieval_request_keeps_principal_and_library_separate() -> None:
    request = RetrievalRequest(
        principal=make_principal(), library_id=uuid4(), query="evidence", limit=8
    )
    assert request.principal.user_id != request.library_id
    assert request.model_dump(mode="json")["limit"] == 8


def test_retrieval_request_serializes_uuids_as_json_strings() -> None:
    request = RetrievalRequest(principal=make_principal(), library_id=uuid4(), query="evidence")
    payload = request.model_dump(mode="json")
    assert payload["library_id"] == str(request.library_id)
    assert payload["principal"]["user_id"] == str(request.principal.user_id)


def test_retrieval_request_round_trips_through_json() -> None:
    request = RetrievalRequest(principal=make_principal(), library_id=uuid4(), query="evidence")
    assert RetrievalRequest.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize("limit", [0, 51])
def test_retrieval_limit_is_bounded(limit: int) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(
            principal=make_principal(), library_id=uuid4(), query="evidence", limit=limit
        )


def test_retrieval_query_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(principal=make_principal(), library_id=uuid4(), query="   ")


def test_models_reject_unknown_fields() -> None:
    # ty flags both of the next two calls, which is the contract working: these
    # tests assert the same strictness holds at runtime, not only statically.
    with pytest.raises(ValidationError):
        Principal(subject="oidc-user", user_id=uuid4(), groups=(), is_admin=True)  # ty: ignore[unknown-argument]


def test_models_are_immutable() -> None:
    principal = make_principal()
    with pytest.raises(ValidationError):
        principal.subject = "someone-else"  # ty: ignore[invalid-assignment]


def test_principal_requires_a_non_empty_subject() -> None:
    with pytest.raises(ValidationError):
        Principal(subject="", user_id=uuid4())


def test_principal_groups_default_to_empty_and_stay_a_tuple() -> None:
    principal = Principal(subject="oidc-user", user_id=uuid4())
    assert principal.groups == ()
    assert isinstance(Principal(subject="s", user_id=uuid4(), groups=["a"]).groups, tuple)


def test_citations_reference_document_versions_not_paths() -> None:
    citation = Citation(
        document_id=uuid4(),
        document_version_id=uuid4(),
        chunk_id=uuid4(),
        locator=SourceLocator(page=4),
        excerpt="the cited passage",
    )
    payload = citation.model_dump(mode="json")
    assert "path" not in payload
    assert payload["document_version_id"] == str(citation.document_version_id)


def test_source_locator_pages_are_one_based() -> None:
    with pytest.raises(ValidationError):
        SourceLocator(page=0)


def test_retrieved_chunk_carries_scope_for_authorization_filters() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        library_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="passage",
        score=0.71,
        locator=SourceLocator(section="Methods"),
    )
    assert {"library_id", "document_version_id"} <= chunk.model_dump().keys()


def test_chat_request_defaults_to_a_new_conversation_without_tools() -> None:
    request = ChatRequest(principal=make_principal(), library_id=uuid4(), message="hello")
    assert request.conversation_id is None
    assert request.tools_enabled is False


def test_library_summary_exposes_owner_without_assuming_it_is_the_caller() -> None:
    now = datetime.now(UTC)
    summary = LibrarySummary(
        id=uuid4(), name="Thesis", owner_user_id=uuid4(), created_at=now, updated_at=now
    )
    assert summary.document_count == 0


def test_library_names_are_trimmed_and_bounded() -> None:
    now = datetime.now(UTC)
    summary = LibrarySummary(
        id=uuid4(), name="  Thesis  ", owner_user_id=uuid4(), created_at=now, updated_at=now
    )
    assert summary.name == "Thesis"
    with pytest.raises(ValidationError):
        LibrarySummary(
            id=uuid4(), name=" " * 5, owner_user_id=uuid4(), created_at=now, updated_at=now
        )


def test_document_summary_reports_a_known_ingestion_status() -> None:
    now = datetime.now(UTC)
    document = DocumentSummary(
        id=uuid4(),
        library_id=uuid4(),
        current_version_id=uuid4(),
        filename="paper.pdf",
        media_type="application/pdf",
        byte_size=1024,
        status=IngestionStatus.READY,
        created_at=now,
        updated_at=now,
    )
    assert document.model_dump(mode="json")["status"] == "ready"


def test_problem_detail_uses_stable_machine_readable_codes() -> None:
    problem = ProblemDetail(
        code=ErrorCode.IDENTITY_MISSING,
        title="Identity missing",
        status=401,
        detail="The edge did not supply a trusted subject.",
        request_id="01J0",
    )
    assert problem.model_dump(mode="json")["code"] == "identity_missing"

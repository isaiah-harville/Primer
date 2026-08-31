"""The Retrieval service.

Every route takes a principal, a library, and a generation. Those are not
optional and have no defaults: a request that could omit its scope would, on
the day a caller forgot, return another user's documents. Pydantic rejects
such a request with 422 before any store is reached.

The principal is audit context, not authorization. Whether this caller may
read this library was decided by Control before the request was made;
repeating that decision here without Control's data would mean guessing.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from haystack.document_stores.types import DocumentStore, DuplicatePolicy
from primer_contracts.indexing import (
    DeleteRequest,
    DeleteResult,
    GenerationCount,
    GenerationQuery,
    IndexRequest,
    IndexResult,
    SearchRequest,
    SearchResult,
)

from primer_retrieval import __version__
from primer_retrieval.config import Settings
from primer_retrieval.errors import ProblemError, problem_response
from primer_retrieval.pipelines import (
    DocumentEmbedder,
    TextEmbedder,
    build_document_embedder,
    build_retriever,
    build_text_embedder,
    scope_filter,
    to_documents,
    to_retrieved,
)
from primer_retrieval.security import require_service_credential
from primer_retrieval.stores import build_document_store

router = APIRouter(
    prefix="/internal/v1",
    dependencies=[Depends(require_service_credential)],
    include_in_schema=False,
)


class RetrievalState:
    """Everything a request needs, built once at startup."""

    def __init__(
        self,
        settings: Settings,
        store: DocumentStore,
        document_embedder: DocumentEmbedder,
        text_embedder: TextEmbedder,
        retriever: Any | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.document_embedder = document_embedder
        self.text_embedder = text_embedder
        self.retriever = retriever if retriever is not None else build_retriever(store, settings)


def get_state(request: Request) -> RetrievalState:
    state: RetrievalState = request.app.state.retrieval
    return state


State = Annotated[RetrievalState, Depends(get_state)]


@router.post("/index", summary="Write one generation's chunks")
def index_chunks(payload: IndexRequest, state: State) -> IndexResult:
    """Write into a pending generation.

    Nothing searches a generation until a caller names it, so a rebuild in
    progress is invisible rather than partially answering questions.

    Duplicate ids overwrite. Chunk ids are derived from version, generation,
    and ordinal, so a stage that ran twice rewrites identical rows instead of
    doubling the index.
    """
    documents = to_documents(payload.chunks, state.document_embedder)
    written = state.store.write_documents(documents, policy=DuplicatePolicy.OVERWRITE)
    return IndexResult(generation_id=payload.generation_id, written=written)


@router.post("/verify", summary="Count what a generation actually holds")
def verify_generation(payload: GenerationQuery, state: State) -> GenerationCount:
    """Report a generation's size so activation can refuse an incomplete index.

    Activating a generation that is short of its expected count would drop
    the missing passages from every future answer, with nothing to show that
    anything was lost.
    """
    documents = state.store.filter_documents(
        filters=scope_filter(payload.library_id, (payload.generation_id,))
    )
    return GenerationCount(generation_id=payload.generation_id, count=len(documents))


@router.post("/search", summary="Search one library")
def search(payload: SearchRequest, state: State) -> SearchResult:
    """Rank passages within one library's active generations.

    The filter is built from the request's scope, never from the query, and
    is applied by the store rather than by discarding results afterwards.
    Filtering after the fact would silently return fewer results than asked
    for, and would depend on this code never being reordered.
    """
    embedded = state.text_embedder.run(payload.query)
    hits = state.retriever.run(
        query_embedding=embedded["embedding"],
        filters=scope_filter(payload.library_id, payload.generation_ids),
        top_k=payload.limit,
    )
    return SearchResult(chunks=tuple(to_retrieved(hit) for hit in hits["documents"]))


@router.post("/delete", summary="Remove one generation's chunks")
def delete_generation(payload: DeleteRequest, state: State) -> DeleteResult:
    """Delete by generation, which makes retiring and erasing the same act.

    Deleting nothing is success. A repeated delete has to be safe: it is
    exactly what a redelivered cleanup message asks for.
    """
    documents = state.store.filter_documents(
        filters=scope_filter(payload.library_id, (payload.generation_id,))
    )
    if documents:
        state.store.delete_documents([document.id for document in documents])
    return DeleteResult(generation_id=payload.generation_id, deleted=len(documents))


@router.get("/health/live", summary="Process liveness", dependencies=[])
def live() -> dict[str, str]:
    return {"status": "ok"}


def create_app(
    settings: Settings | None = None,
    store: DocumentStore | None = None,
    document_embedder: DocumentEmbedder | None = None,
    text_embedder: TextEmbedder | None = None,
    retriever: Any | None = None,
) -> FastAPI:
    """Build the Retrieval service.

    The store and embedders are injected rather than read from globals so a
    test can run the real filtering logic against a real backend without an
    embedding endpoint, which is what makes the conformance suite possible.
    """
    settings = settings or Settings()
    app = FastAPI(
        title="Primer Retrieval",
        version=__version__,
        summary="The exclusive owner of Primer's vector stores",
    )
    app.state.settings = settings
    app.state.retrieval = RetrievalState(
        settings,
        store or build_document_store(settings),
        document_embedder or build_document_embedder(settings),
        text_embedder or build_text_embedder(settings),
        retriever,
    )

    @app.exception_handler(ProblemError)
    async def _handle_problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc)

    app.include_router(router)
    return app

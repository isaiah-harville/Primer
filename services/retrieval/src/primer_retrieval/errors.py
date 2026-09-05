"""Failures only Retrieval can raise.

The envelope they travel in - `ProblemError`, `problem_response` - is
`primer_service.errors`, and is imported from there directly by whatever
needs it. This module re-exports none of it: a name that arrives through a
second module is a name whose home you have to go and look for.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import status
from primer_contracts.errors import ErrorCode
from primer_service.errors import ProblemError

logger = logging.getLogger(__name__)


def dependency_unavailable(detail: str) -> ProblemError:
    return ProblemError(
        code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        title="Retrieval dependency unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


@contextmanager
def embedding_endpoint(consequence: str) -> Iterator[None]:
    """Mark a block that cannot run without the embedding endpoint.

    An unreachable embedder is a deployment fault, not a bad request, and it
    is the single most likely thing to be wrong on a self-hosted install: it
    is a separate process that has to be running and reachable. Left
    unhandled it surfaces as a bare 500, and a 500 is the shape every
    unrelated bug also has - so whoever reads it goes looking at Primer
    rather than at the endpoint that is actually down.

    `consequence` completes the sentence the caller reads, because what
    cannot happen is the part that differs: a library that cannot be
    searched and a document that cannot be indexed are the same fault
    arriving at two different people.

    Everything is caught, not one exception type. The embedder is a library
    call over a network to somebody else's server, and what it raises for a
    refused connection, a timeout, a bad key, or a model that is not loaded
    is not a set this module can enumerate and should not pretend to.
    """
    try:
        yield
    except Exception as error:
        logger.warning("the embedding endpoint could not be reached", exc_info=True)
        raise dependency_unavailable(
            f"The embedding endpoint could not be reached, so {consequence}."
        ) from error


#: What a store says when a vector's width does not match its column.
#: pgvector phrases it "expected 384 dimensions, not 1024"; the numbers are
#: what matter, and they are the two an operator needs to see.
DIMENSION_MISMATCH = re.compile(r"expected (\d+) dimensions?, not (\d+)", re.IGNORECASE)


def wrong_dimensions(stored: str, offered: str, consequence: str) -> ProblemError:
    """The embedding model was changed without rebuilding the store.

    A conflict rather than an unavailable dependency, and deliberately a 4xx:
    nothing is down and nothing is coming back. A worker reading this must
    stop rather than retry, because every retry will be refused identically
    and the budget spent before anyone is told.

    This is the one failure the chart warns about and cannot check for
    itself - the vector column keeps the width it was created with, so a
    deployment that swaps embedding models looks healthy right up until the
    first document is indexed.
    """
    return ProblemError(
        code=ErrorCode.CONFLICT,
        title="Embedding size does not match the vector store",
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"The vector store holds {stored}-dimensional vectors and this deployment is "
            f"producing {offered}-dimensional ones, so {consequence}. A vector column keeps "
            "the width it was created with, so changing the embedding model means dropping "
            "the vectors table and reindexing, or setting the model back to the one that "
            "matches."
        ),
    )


@contextmanager
def vector_store(consequence: str) -> Iterator[None]:
    """Mark a block that cannot run unless the vector store accepts a write.

    Writing is the half of the store that was never guarded. A search that
    could not reach its backend said so; an index that could not write to it
    raised, became a bare 500, and reached the user as "Retrieval answered
    500" - which says only that Retrieval was reached, and sends whoever
    reads it nowhere in particular.

    Everything is caught rather than one exception type: what a document
    store raises for a refused connection, a full disk, a schema that does
    not match, or a driver that has given up is a set that changes with the
    backend, and this module should not pretend to enumerate it.
    """
    try:
        yield
    except Exception as error:
        mismatch = DIMENSION_MISMATCH.search(str(error))
        if mismatch:
            logger.error("the vector store column does not match the embedding model")
            raise wrong_dimensions(mismatch.group(1), mismatch.group(2), consequence) from error
        logger.warning("the vector store refused a write", exc_info=True)
        raise dependency_unavailable(
            f"The vector store could not be written to, so {consequence}."
        ) from error

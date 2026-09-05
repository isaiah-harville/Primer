"""Failures only Retrieval can raise.

The envelope they travel in - `ProblemError`, `problem_response` - is
`primer_service.errors`, and is imported from there directly by whatever
needs it. This module re-exports none of it: a name that arrives through a
second module is a name whose home you have to go and look for.
"""

from __future__ import annotations

import logging
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

"""Failures only Retrieval can raise.

The envelope they travel in - `ProblemError`, `problem_response` - is
`primer_service.errors`, and is imported from there directly by whatever
needs it. This module re-exports none of it: a name that arrives through a
second module is a name whose home you have to go and look for.
"""

from __future__ import annotations

from fastapi import status
from primer_contracts.errors import ErrorCode
from primer_service.errors import ProblemError


def dependency_unavailable(detail: str) -> ProblemError:
    return ProblemError(
        code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        title="Retrieval dependency unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )

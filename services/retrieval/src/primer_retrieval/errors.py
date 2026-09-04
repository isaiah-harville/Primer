"""Retrieval's own failures, in Primer's shared problem envelope.

The envelope - `ProblemError`, `problem_response` - is
`primer_service.errors`, shared with Control and Chat. What is here is what
only this service can say.
"""

from __future__ import annotations

from fastapi import status
from primer_contracts.errors import ErrorCode
from primer_service.errors import PROBLEM_MEDIA_TYPE, ProblemError, problem_response

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "ProblemError",
    "dependency_unavailable",
    "problem_response",
]


def dependency_unavailable(detail: str) -> ProblemError:
    return ProblemError(
        code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        title="Retrieval dependency unavailable",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )

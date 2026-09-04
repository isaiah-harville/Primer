"""Chat's own failures, in Primer's shared problem envelope.

The envelope - `ProblemError`, `problem_response`, `validation_problem` - is
`primer_service.errors`, shared with Control and Retrieval. What is here is
what only this service can say.
"""

from __future__ import annotations

from fastapi import status
from primer_contracts.errors import ErrorCode
from primer_service.errors import (
    PROBLEM_MEDIA_TYPE,
    ProblemError,
    problem_response,
    rendered,
    validation_problem,
)

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "ProblemError",
    "not_found",
    "problem_response",
    "rendered",
    "validation_problem",
]


def not_found(what: str) -> ProblemError:
    """Absence and denial look alike, as everywhere else in Primer."""
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title=f"{what} not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No {what.lower()} with that identifier is available to you.",
    )

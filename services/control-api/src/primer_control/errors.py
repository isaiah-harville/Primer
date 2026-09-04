"""The Control API's own failures, in Primer's shared problem envelope.

The envelope - `ProblemError`, `problem_response`, `validation_problem` - is
`primer_service.errors`, shared with Chat and Retrieval. What is here is what
only this service can say.
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
    "identity_missing",
    "problem_response",
    "rendered",
    "validation_problem",
]


def identity_missing() -> ProblemError:
    return ProblemError(
        code=ErrorCode.IDENTITY_MISSING,
        title="Identity missing",
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="The authenticating proxy did not supply a trusted subject.",
    )

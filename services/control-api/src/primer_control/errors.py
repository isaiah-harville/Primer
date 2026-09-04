"""Failures only the Control API can raise.

The envelope they travel in - `ProblemError`, `problem_response`,
`validation_problem` - is `primer_service.errors`, and is imported from there
directly by whatever needs it. This module re-exports none of it: a name that
arrives through a second module is a name whose home you have to go and look
for.
"""

from __future__ import annotations

from fastapi import status
from primer_contracts.errors import ErrorCode
from primer_service.errors import ProblemError


def identity_missing() -> ProblemError:
    return ProblemError(
        code=ErrorCode.IDENTITY_MISSING,
        title="Identity missing",
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="The authenticating proxy did not supply a trusted subject.",
    )

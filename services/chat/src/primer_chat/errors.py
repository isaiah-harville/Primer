"""Failures only Chat can raise.

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


def not_found(what: str) -> ProblemError:
    """Absence and denial look alike, as everywhere else in Primer."""
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title=f"{what} not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No {what.lower()} with that identifier is available to you.",
    )

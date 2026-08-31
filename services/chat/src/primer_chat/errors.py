"""RFC 9457-style errors, matching the other services."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from primer_contracts.errors import ErrorCode, ProblemDetail

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self, code: ErrorCode, title: str, status_code: int, detail: str | None = None
    ) -> None:
        super().__init__(title)
        self.code = code
        self.title = title
        self.status_code = status_code
        self.detail = detail


def not_found(what: str) -> ProblemError:
    """Absence and denial look alike, as everywhere else in Primer."""
    return ProblemError(
        code=ErrorCode.NOT_FOUND,
        title=f"{what} not found",
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No {what.lower()} with that identifier is available to you.",
    )


def problem_response(request: Request, error: ProblemError) -> JSONResponse:
    problem = ProblemDetail(
        code=error.code,
        title=error.title,
        status=error.status_code,
        detail=error.detail,
        request_id=request.headers.get("X-Request-ID"),
    )
    return JSONResponse(
        status_code=error.status_code,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )

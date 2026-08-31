"""RFC 9457-style error responses built on the shared contract."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from primer_contracts.errors import ErrorCode, ProblemDetail

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    """An error that renders as a `ProblemDetail` body.

    Messages here are user-facing and must stay sanitized; operational
    context belongs in logs, correlated by request ID.
    """

    def __init__(
        self, code: ErrorCode, title: str, status_code: int, detail: str | None = None
    ) -> None:
        super().__init__(title)
        self.code = code
        self.title = title
        self.status_code = status_code
        self.detail = detail


def identity_missing() -> ProblemError:
    return ProblemError(
        code=ErrorCode.IDENTITY_MISSING,
        title="Identity missing",
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="The authenticating proxy did not supply a trusted subject.",
    )


def problem_response(request: Request, error: ProblemError) -> JSONResponse:
    problem = ProblemDetail(
        code=error.code,
        title=error.title,
        status=error.status_code,
        detail=error.detail,
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        status_code=error.status_code,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )

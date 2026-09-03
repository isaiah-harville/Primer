"""RFC 9457-style errors, matching the other services."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
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


#: Where a rejected field sits in the request, as FastAPI reports it. The
#: first element says which part - body, query, path - and is not worth
#: repeating back to someone who can see the form they just submitted.
def _field_of(location: tuple[object, ...]) -> str:
    parts = [str(part) for part in location[1:]] or [str(part) for part in location]
    return ".".join(parts)


def validation_problem(error: RequestValidationError) -> ProblemDetail:
    """Turn FastAPI's validation errors into the error shape Primer promises.

    Every other failure here is an RFC 9457 problem document, but a request
    that fails validation is caught by the framework before any of Primer's
    code runs, and FastAPI answers in its own shape: a list of objects under
    `detail`. Clients written against the contract read `detail` as a string,
    so a rejected field arrived on a user's screen as "[object Object]".

    The rejected input itself is deliberately not echoed: it is already on
    the user's screen, and it is the one part of this that could be anything.
    """
    described = "; ".join(
        f"{_field_of(tuple(fault.get('loc', ())))}: {fault.get('msg', 'is not valid')}"
        for fault in error.errors()
    )
    return ProblemDetail(
        code=ErrorCode.VALIDATION_FAILED,
        title="Request could not be accepted",
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=described or "The request was not in the expected shape.",
    )


def problem_response(request: Request, error: ProblemError) -> JSONResponse:
    problem = ProblemDetail(
        code=error.code,
        title=error.title,
        status=error.status_code,
        detail=error.detail,
        request_id=request.headers.get("X-Request-ID"),
    )
    return rendered(request, problem)


def rendered(request: Request, problem: ProblemDetail) -> JSONResponse:
    """One place that decides what a problem looks like on the wire."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_copy(
            update={"request_id": request.headers.get("X-Request-ID")}
        ).model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )

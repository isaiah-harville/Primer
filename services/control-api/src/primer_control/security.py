"""The credential guarding the cluster-internal worker API.

This boundary is not the user identity boundary. User requests arrive
through the edge proxy with trusted identity headers; worker requests arrive
from inside the cluster with a shared service credential and act on jobs
rather than on behalf of a person.
"""

from __future__ import annotations

from hmac import compare_digest

from fastapi import Request, status
from primer_contracts.errors import ErrorCode
from primer_service.errors import ProblemError

from primer_control.config import Settings

SERVICE_TOKEN_HEADER = "X-Primer-Service-Token"  # noqa: S105 - a header name, not a secret


def require_service_credential(request: Request) -> None:
    """Reject anything without the configured service credential.

    An unset token denies every request rather than allowing them. The
    alternative - treating "no credential configured" as "no credential
    required" - turns a missing environment variable into an open internal
    API, which is exactly the failure that must never be silent.
    """
    settings: Settings = request.app.state.settings
    configured = settings.internal_api_token
    presented = request.headers.get(SERVICE_TOKEN_HEADER, "")

    # Compared as bytes and always compared, so neither a non-ASCII header
    # nor an early return leaks anything about the expected value.
    expected = configured.get_secret_value().encode() if configured is not None else b""
    if not configured or not compare_digest(presented.encode(), expected):
        raise ProblemError(
            code=ErrorCode.IDENTITY_INVALID,
            title="Service credential required",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This endpoint is reachable only from inside the cluster.",
        )

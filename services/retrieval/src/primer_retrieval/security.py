"""The credential guarding this cluster-internal API.

Deliberately a copy of the Control API's check rather than a shared import:
the two services hold different credentials and neither should be able to
present the other's. When a third service needs this, the duplication is the
signal to extract a shared service package - not before, when extracting it
would only couple two things that happen to look alike.
"""

from __future__ import annotations

from hmac import compare_digest

from fastapi import Request, status
from primer_contracts.errors import ErrorCode

from primer_retrieval.config import Settings
from primer_retrieval.errors import ProblemError

SERVICE_TOKEN_HEADER = "X-Primer-Service-Token"  # noqa: S105 - a header name, not a secret


def require_service_credential(request: Request) -> None:
    """Reject anything without the configured service credential.

    An unset token denies every request. Treating "none configured" as "none
    required" would turn a missing environment variable into an open path to
    every library's contents.
    """
    settings: Settings = request.app.state.settings
    configured = settings.internal_api_token
    presented = request.headers.get(SERVICE_TOKEN_HEADER, "")

    expected = configured.get_secret_value().encode() if configured is not None else b""
    if not configured or not compare_digest(presented.encode(), expected):
        raise ProblemError(
            code=ErrorCode.IDENTITY_INVALID,
            title="Service credential required",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This endpoint is reachable only from inside the cluster.",
        )

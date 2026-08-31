"""Stable, machine-readable error contracts (RFC 9457 style)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from primer_contracts.base import WireModel


class ErrorCode(StrEnum):
    """Error codes clients may branch on. Values are part of the contract."""

    IDENTITY_MISSING = "identity_missing"
    IDENTITY_INVALID = "identity_invalid"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION_FAILED = "validation_failed"
    UNSUPPORTED_CONTENT = "unsupported_content"
    QUOTA_EXCEEDED = "quota_exceeded"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL_ERROR = "internal_error"


class ProblemDetail(WireModel):
    """Sanitized error body. Operational context stays in logs, not here."""

    code: ErrorCode
    title: str = Field(min_length=1, max_length=255)
    status: int = Field(ge=400, le=599)
    detail: str | None = Field(default=None, max_length=2000)
    request_id: str | None = Field(default=None, max_length=64)

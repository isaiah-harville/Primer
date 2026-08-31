"""The internal principal that services authorize against.

`Principal` is derived by the Control API from trusted edge identity. It is
never populated directly from a browser-supplied header by any other service.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from primer_contracts.base import WireModel


class Principal(WireModel):
    """An authenticated Primer identity acting on a request."""

    subject: str = Field(min_length=1, max_length=255, description="Stable OIDC `sub` claim")
    user_id: UUID = Field(description="Primer-internal user identifier")
    groups: tuple[str, ...] = Field(
        default=(), description="Operator-policy groups; never an implicit grant to resources"
    )
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)

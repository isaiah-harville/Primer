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


class DeploymentCapabilities(WireModel):
    """What this deployment can actually do, as the browser needs to know it.

    Sent to the web app so it can hide what will not work rather than
    offering it and failing. Every field is a checked fact or an operator's
    declaration - none is inferred from a model's name.
    """

    #: False means every request is one fixed local user. The interface warns
    #: about this permanently: it is the difference between a private
    #: notebook and an open one.
    auth_enabled: bool
    #: Nothing can be indexed without embeddings, so nothing can be asked.
    ingestion_available: bool
    chat_available: bool
    tools_available: bool
    max_upload_bytes: int = Field(ge=0)
    supported_extensions: tuple[str, ...] = ()

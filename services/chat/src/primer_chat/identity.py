"""The same identity boundary the Control API uses.

Chat trusts headers injected by the authenticating proxy and derives the
same internal user id from the same subject, so a conversation started
through one service is owned by the same person in the other.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request, status
from primer_contracts.errors import ErrorCode
from primer_contracts.identity import Principal, is_admin

from primer_chat.config import Settings
from primer_chat.errors import ProblemError

#: The same namespace Control uses. A different one here would give the same
#: person two identities and hide their own libraries from their own chats.
PRIMER_USER_NAMESPACE = uuid.UUID("6f2f5a10-9f4b-5f0e-9b53-7a1a5c6d8e10")
LOCAL_SUBJECT = "primer-local-user"


def user_id_for_subject(subject: str) -> uuid.UUID:
    return uuid.uuid5(PRIMER_USER_NAMESPACE, subject)


def get_principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    if settings.auth_mode != "oidc":
        # Headers are ignored entirely, not defaulted: a deployment with auth
        # off must not behave differently because someone sent a header.
        return Principal(subject=LOCAL_SUBJECT, user_id=user_id_for_subject(LOCAL_SUBJECT))

    subject = request.headers.get(settings.subject_header, "").strip()
    if not subject:
        raise ProblemError(
            code=ErrorCode.IDENTITY_MISSING,
            title="Identity missing",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authenticating proxy did not supply a trusted subject.",
        )
    return Principal(
        subject=subject,
        user_id=user_id_for_subject(subject),
        email=request.headers.get(settings.email_header) or None,
        groups=_groups_from(request.headers.get(settings.groups_header), settings.groups_delimiter),
    )


def _groups_from(raw: str | None, delimiter: str) -> tuple[str, ...]:
    """The groups the proxy asserted, which is the whole of the admin test."""
    if not raw:
        return ()
    return tuple(group.strip() for group in raw.split(delimiter) if group.strip())


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_admin(request: Request, principal: CurrentPrincipal) -> Principal:
    """Refuse anyone who may not change how this deployment is wired.

    403 rather than the 404 used for libraries. Absence and denial are worth
    conflating for a resource whose existence is itself private; a
    deployment's settings page is not private in that way, and telling an
    ordinary user "not for you" is more useful than pretending the page does
    not exist.
    """
    settings: Settings = request.app.state.settings
    allowed = is_admin(
        principal,
        auth_enabled=settings.auth_mode == "oidc",
        admin_group=settings.admin_group,
    )
    if not allowed:
        raise ProblemError(
            code=ErrorCode.IDENTITY_INVALID,
            title="Not an administrator",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Changing this deployment's settings is restricted to administrators.",
        )
    return principal


CurrentAdmin = Annotated[Principal, Depends(require_admin)]

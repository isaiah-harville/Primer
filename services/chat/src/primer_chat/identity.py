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
from primer_contracts.identity import Principal

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
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]

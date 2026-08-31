"""Turn trusted edge identity into an internal `Principal`.

The edge (`oauth2-proxy`) strips client-supplied identity headers and injects
its own after authenticating. This module therefore trusts the configured
headers in OIDC mode and, critically, ignores them entirely in disabled mode
so a spoofed header cannot manufacture an identity in a local deployment.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from primer_contracts.identity import Principal

from primer_control.config import Settings
from primer_control.errors import identity_missing

#: Namespace for deriving stable user UUIDs from OIDC subjects. Persisting a
#: users table (a later task) supersedes this, but the mapping must already be
#: deterministic so identity does not change between restarts.
PRIMER_USER_NAMESPACE = uuid.UUID("6f2f5a10-9f4b-5f0e-9b53-7a1a5c6d8e10")

LOCAL_SUBJECT = "primer-local-user"
LOCAL_USER_ID = uuid.uuid5(PRIMER_USER_NAMESPACE, LOCAL_SUBJECT)


def user_id_for_subject(subject: str) -> uuid.UUID:
    """Derive a stable Primer user id from an OIDC subject."""
    return uuid.uuid5(PRIMER_USER_NAMESPACE, subject)


def local_principal() -> Principal:
    """The single identity used when authentication is disabled."""
    return Principal(subject=LOCAL_SUBJECT, user_id=LOCAL_USER_ID, groups=())


def _groups_from_header(raw: str | None, delimiter: str) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(group.strip() for group in raw.split(delimiter) if group.strip())


def principal_from_request(request: Request, settings: Settings) -> Principal:
    """Map the current request to an internal principal."""
    if not settings.auth_enabled:
        return local_principal()

    subject = (request.headers.get(settings.subject_header) or "").strip()
    if not subject:
        raise identity_missing()

    email = (request.headers.get(settings.email_header) or "").strip() or None
    groups = _groups_from_header(
        request.headers.get(settings.groups_header), settings.groups_delimiter
    )
    return Principal(
        subject=subject, user_id=user_id_for_subject(subject), groups=groups, email=email
    )


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_principal(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Principal:
    """FastAPI dependency yielding the acting principal."""
    return principal_from_request(request, settings)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]

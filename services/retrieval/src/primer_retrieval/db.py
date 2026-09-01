"""Connection string handling shared by the service and its migrations."""

from __future__ import annotations

#: The driver migrations run under. Synchronous, and the same one the vector
#: integration itself speaks, so a deployment needs one Postgres driver
#: installed rather than two.
SYNC_DRIVER = "psycopg"


def as_sync_url(url: str) -> str:
    """Name the driver SQLAlchemy should use, rewriting only the scheme.

    The service hands its connection string straight to the vector
    integration, so `PRIMER_DATABASE_URL` usually carries no driver at all,
    and SQLAlchemy reads a bare `postgresql://` as psycopg 2 - which is not
    installed and should not be. An async driver is replaced rather than
    rejected, because one deployment may hand every service the same string
    and the services that serve requests do want asyncpg.

    Only the part before `://` is touched. A password is free to contain
    anything, `+asyncpg` included, and rewriting the whole string would
    quietly corrupt it into an authentication failure with no visible cause.
    """
    scheme, separator, rest = url.partition("://")
    if not separator or not scheme.startswith("postgresql"):
        return url
    return f"postgresql+{SYNC_DRIVER}{separator}{rest}"

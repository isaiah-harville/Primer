"""Connection string handling shared by the service and its migrations.

Retrieval owns no async session - it hands its connection string straight to
the vector integration - so only the driver rewriting is wanted here, and
that now comes from `primer_service.db` along with everyone else's.

`PRIMER_DATABASE_URL` usually carries no driver at all, and SQLAlchemy reads
a bare `postgresql://` as psycopg 2, which is not installed and should not
be. One deployment may hand every service the same string, so an async driver
is rewritten rather than rejected.
"""

from __future__ import annotations

from primer_service.db import SYNC_DRIVER, as_sync_url

__all__ = ["SYNC_DRIVER", "as_sync_url"]

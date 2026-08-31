"""Integration fixtures backed by a real PostgreSQL.

Persistence and authorization bugs hide behind mocks, so these tests run
against the same image the deployment uses. The container is session-scoped
because starting PostgreSQL costs far more than isolating a test inside it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient
from primer_control.app import create_app
from primer_control.config import Settings
from primer_control.db import Database, as_sync_url
from primer_control.migrations import upgrade_to_head
from sqlalchemy.ext.asyncio import AsyncEngine
from support import UserClient
from testcontainers.community.postgres import PostgresContainer

#: pgvector rather than plain postgres: the Control schema does not need it,
#: but the default Compose profile ships it and the later retrieval
#: conformance suite reuses this fixture.
POSTGRES_IMAGE = "pgvector/pgvector:pg17"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """A database with the Control schema at head.

    Migrations run once here, never from application startup, matching how
    Compose and Helm apply them as an explicit step.
    """
    upgrade_to_head(postgres_url)
    return postgres_url


@pytest.fixture
def scratch_db_url(postgres_url: str) -> Iterator[str]:
    """A throwaway database in the same container, for destructive tests."""
    from sqlalchemy import create_engine, text

    admin = create_engine(as_sync_url(postgres_url), isolation_level="AUTOCOMMIT")
    name = "primer_scratch"
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield postgres_url.rsplit("/", 1)[0] + f"/{name}"
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest_asyncio.fixture
async def database(migrated_url: str) -> AsyncIterator[Database]:
    db = Database(migrated_url)
    yield db
    await db.dispose()


@pytest_asyncio.fixture
async def clean_tables(database: Database) -> AsyncIterator[AsyncEngine]:
    """Truncate between tests so each one starts from a known empty schema."""
    from sqlalchemy import text

    async with database.engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE control.libraries, control.users RESTART IDENTITY CASCADE")
        )
    yield database.engine


@pytest_asyncio.fixture
async def client(database: Database, clean_tables: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """An OIDC-mode client; each request names its user through edge headers."""
    app = create_app(Settings(auth_mode="oidc"), database=database)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://control") as http:
        yield http


@pytest.fixture
def owner(client: AsyncClient) -> UserClient:
    return UserClient(client, "oidc-owner")


@pytest.fixture
def stranger(client: AsyncClient) -> UserClient:
    return UserClient(client, "oidc-stranger")

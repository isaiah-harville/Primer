"""Async database access for the Control API.

The engine and session factory are held on an injected `Database` rather than
in module globals, so an application, a migration run, and a test can each
own their own connections without fighting over process state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def as_async_url(url: str) -> str:
    """Normalize a PostgreSQL URL onto the asyncpg driver."""
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def as_sync_url(url: str) -> str:
    """Normalize a PostgreSQL URL onto psycopg.

    Alembic runs synchronously, so migrations use psycopg while the
    application serves requests over asyncpg from the same URL.
    """
    url = url.replace("+asyncpg", "")
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


class Database:
    """Owns the async engine and hands out transactional sessions."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(as_async_url(url), echo=echo, future=True)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session whose transaction commits on success and rolls back on error."""
        async with self._sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def check(self) -> bool:
        """Readiness probe: can this service actually reach PostgreSQL?"""
        from sqlalchemy import text

        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - any failure to reach PostgreSQL means unready
            return False
        return True

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a per-request transactional session."""
    database: Database = request.app.state.database
    async with database.session() as session:
        yield session

"""Async database access for the Chat service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from primer_service.durable import SESSION_STATE
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _with_driver(url: str, driver: str) -> str:
    """Rewrite only the scheme.

    A password may contain anything, a driver name included, so replacing
    across the whole string would corrupt it into an authentication failure
    with nothing on the surface to explain why.
    """
    scheme, separator, rest = url.partition("://")
    if not separator or not scheme.startswith("postgresql"):
        return url
    return f"postgresql+{driver}{separator}{rest}"


def as_async_url(url: str) -> str:
    """The driver the application serves requests over."""
    return _with_driver(url, "asyncpg")


def as_sync_url(url: str) -> str:
    """Alembic runs synchronously; the application serves over asyncpg."""
    return _with_driver(url, "psycopg")


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(as_async_url(url), echo=echo, future=True)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def check(self) -> bool:
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
    database: Database = request.app.state.database
    async with database.session() as session:
        # Left where `DurableRoute` can find it, so the write is
        # committed before the response is sent rather than in this
        # dependency's teardown - which FastAPI runs afterwards, so a
        # client that read its own write back could miss it.
        setattr(request.state, SESSION_STATE, session)
        yield session

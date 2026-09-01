"""Approving a tool call, and the many ways one must not run.

Every test here is about a call that does not execute. The failure this
guards against is somebody else's pending shell command being approved, or a
stale approval running long after the person who granted it walked away.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from chat_support import LIBRARY_ID, ChatUser
from httpx2 import AsyncClient
from primer_chat.db import Database
from primer_chat.models import ToolCall
from primer_chat.tool_repository import ToolRepository
from primer_contracts.chat import ToolPhase
from sqlalchemy import select


async def conversation_for(user: ChatUser) -> str:
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    return events[-1]["message"]["conversation_id"]


async def request_tool(
    database: Database, conversation_id: str, *, ttl_seconds: int = 300
) -> ToolCall:
    async with database.session() as session:
        return await ToolRepository(session).record_request(
            conversation_id=uuid.UUID(conversation_id),
            tool_name="sandbox.shell",
            server_name="sandbox",
            arguments={"command": "ls -la"},
            ttl_seconds=ttl_seconds,
        )


@pytest.fixture
def owner(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "owner")


@pytest.fixture
def stranger(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "stranger")


@pytest_asyncio.fixture
async def pending(owner: ChatUser, database: Database) -> ToolCall:
    return await request_tool(database, await conversation_for(owner))


async def test_a_request_is_audited_before_anyone_decides(
    pending: ToolCall, database: Database
) -> None:
    """A refused tool is exactly what someone will later want to see refused."""
    async with database.session() as session:
        stored = (await session.execute(select(ToolCall))).scalar_one()

    assert stored.phase == ToolPhase.REQUESTED.value
    assert stored.arguments == {"command": "ls -la"}
    assert stored.decided_by is None


async def test_approving_records_who_decided(owner: ChatUser, pending: ToolCall) -> None:
    response = await owner.post(f"/api/v1/tool-requests/{pending.id}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "approved"
    assert body["decided_by"] == "owner"
    assert body["decided_at"] is not None


async def test_the_arguments_are_shown_back(owner: ChatUser, pending: ToolCall) -> None:
    """Approving 'run a command' without seeing the command is not consent."""
    listed = (await owner.get("/api/v1/tool-requests")).json()

    assert listed[0]["arguments"] == {"command": "ls -la"}
    assert listed[0]["tool_name"] == "sandbox.shell"


async def test_a_stranger_cannot_approve_someone_elses_call(
    stranger: ChatUser, pending: ToolCall, database: Database
) -> None:
    """The worst thing this service could allow."""
    response = await stranger.post(f"/api/v1/tool-requests/{pending.id}/approve")

    assert response.status_code == 404
    async with database.session() as session:
        stored = (await session.execute(select(ToolCall))).scalar_one()
    assert stored.phase == ToolPhase.REQUESTED.value


async def test_a_stranger_cannot_see_it_either(stranger: ChatUser, pending: ToolCall) -> None:
    assert (await stranger.get("/api/v1/tool-requests")).json() == []


async def test_denying_is_final(owner: ChatUser, pending: ToolCall) -> None:
    """A decided request keeps its first decision."""
    assert (await owner.post(f"/api/v1/tool-requests/{pending.id}/deny")).status_code == 200

    second = await owner.post(f"/api/v1/tool-requests/{pending.id}/approve")

    assert second.status_code == 409
    assert second.json()["code"] == "conflict"


async def test_approving_twice_is_reported_not_ignored(owner: ChatUser, pending: ToolCall) -> None:
    await owner.post(f"/api/v1/tool-requests/{pending.id}/approve")

    again = await owner.post(f"/api/v1/tool-requests/{pending.id}/approve")

    assert again.status_code == 409


async def test_an_expired_request_cannot_be_approved(owner: ChatUser, database: Database) -> None:
    """Approval is consent to one action at one moment."""
    conversation = await conversation_for(owner)
    stale = await request_tool(database, conversation, ttl_seconds=1)
    async with database.engine.begin() as connection:
        from sqlalchemy import text

        await connection.execute(
            text("UPDATE chat.tool_calls SET expires_at = now() - interval '1 hour'")
        )

    response = await owner.post(f"/api/v1/tool-requests/{stale.id}/approve")

    assert response.status_code == 409
    async with database.session() as session:
        stored = (await session.execute(select(ToolCall))).scalar_one()
    assert stored.phase == ToolPhase.EXPIRED.value


async def test_expiry_is_recorded_so_the_audit_says_why(
    owner: ChatUser, database: Database
) -> None:
    """Nothing ran, and the row explains that rather than staying pending."""
    conversation = await conversation_for(owner)
    stale = await request_tool(database, conversation)
    async with database.engine.begin() as connection:
        from sqlalchemy import text

        await connection.execute(
            text("UPDATE chat.tool_calls SET expires_at = now() - interval '1 hour'")
        )

    await owner.post(f"/api/v1/tool-requests/{stale.id}/deny")

    async with database.session() as session:
        stored = (await session.execute(select(ToolCall))).scalar_one()
    assert stored.phase == ToolPhase.EXPIRED.value


async def test_a_request_that_does_not_exist_looks_the_same_as_a_forbidden_one(
    owner: ChatUser,
) -> None:
    response = await owner.post(f"/api/v1/tool-requests/{uuid.uuid4()}/approve")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_only_pending_requests_are_listed(owner: ChatUser, pending: ToolCall) -> None:
    await owner.post(f"/api/v1/tool-requests/{pending.id}/deny")

    assert (await owner.get("/api/v1/tool-requests")).json() == []


async def test_expiry_is_in_the_future_when_recorded(pending: ToolCall) -> None:
    assert pending.expires_at > datetime.now(UTC)
    assert pending.expires_at < datetime.now(UTC) + timedelta(hours=1)

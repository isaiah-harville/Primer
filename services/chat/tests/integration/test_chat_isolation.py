"""Whose conversation it is, and whose library it may read.

The assertions here are mostly about what did *not* happen: a forbidden
question must not reach Retrieval, and must not reach a model. Recording
fakes make that checkable, where a mock returning nothing would look the
same either way.
"""

from __future__ import annotations

import uuid

import pytest
from chat_support import (
    LIBRARY_ID,
    OTHER_LIBRARY_ID,
    ChatUser,
    FakeControl,
    FakeGenerator,
    FakeRetrieval,
)
from httpx2 import AsyncClient


@pytest.fixture
def owner(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "owner")


@pytest.fixture
def stranger(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "stranger")


async def test_a_forbidden_library_never_reaches_retrieval_or_the_model(
    owner: ChatUser, retrieval: FakeRetrieval, generator: FakeGenerator, control: FakeControl
) -> None:
    """The plan's case: authorization happens before anything else runs."""
    events = await owner.ask(str(OTHER_LIBRARY_ID), "What is in the other library?")

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "library_unavailable"
    assert control.asked == [("owner", OTHER_LIBRARY_ID)]
    assert retrieval.searches == []
    assert generator.prompts == []


async def test_a_stranger_cannot_continue_someone_elses_conversation(
    owner: ChatUser, stranger: ChatUser, retrieval: FakeRetrieval, generator: FakeGenerator
) -> None:
    """Guessing a conversation id gets the same 404 as one that never existed."""
    events = await owner.ask(str(LIBRARY_ID), "What is the conclusion?")
    conversation_id = events[-1]["message"]["conversation_id"]
    searches_before = len(retrieval.searches)

    response = await stranger.follow_up(conversation_id, "Tell me more")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert len(retrieval.searches) == searches_before


async def test_a_stranger_cannot_read_the_conversation_or_its_messages(
    owner: ChatUser, stranger: ChatUser
) -> None:
    events = await owner.ask(str(LIBRARY_ID), "What is the conclusion?")
    conversation_id = events[-1]["message"]["conversation_id"]

    assert (await stranger.get(f"/api/v1/conversations/{conversation_id}")).status_code == 404
    assert (
        await stranger.get(f"/api/v1/conversations/{conversation_id}/messages")
    ).status_code == 404
    assert (await stranger.get("/api/v1/conversations")).json() == []


async def test_a_conversation_that_does_not_exist_looks_identical(stranger: ChatUser) -> None:
    """Absence and denial must not be distinguishable."""
    missing = str(uuid.uuid4())
    response = await stranger.get(f"/api/v1/conversations/{missing}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_every_turn_is_authorized_again(owner: ChatUser, control: FakeControl) -> None:
    """Access can be revoked between turns, so it is not decided once."""
    events = await owner.ask(str(LIBRARY_ID), "First question")
    conversation_id = events[-1]["message"]["conversation_id"]

    await owner.follow_up(conversation_id, "Second question")

    assert control.asked == [("owner", LIBRARY_ID), ("owner", LIBRARY_ID)]


async def test_a_library_revoked_mid_conversation_stops_answering(
    owner: ChatUser, control: FakeControl, retrieval: FakeRetrieval
) -> None:
    """A conversation is not a standing grant to the library it was started in."""
    events = await owner.ask(str(LIBRARY_ID), "First question")
    conversation_id = events[-1]["message"]["conversation_id"]
    searches_before = len(retrieval.searches)

    control.allowed = set()
    response = await owner.follow_up(conversation_id, "Second question")

    from chat_support import parse_events

    followup = parse_events(response.text)
    assert followup[-1]["type"] == "error"
    assert followup[-1]["code"] == "library_unavailable"
    assert len(retrieval.searches) == searches_before


async def test_the_search_is_scoped_to_the_conversations_library(
    owner: ChatUser, retrieval: FakeRetrieval, control: FakeControl
) -> None:
    """Retrieval is asked only for what Control authorized."""
    await owner.ask(str(LIBRARY_ID), "What is the conclusion?")

    search = retrieval.searches[0]
    assert search.library_id == LIBRARY_ID
    assert search.generation_ids == control.generations
    assert search.principal.subject == "owner"


async def test_conversations_are_listed_only_to_their_owner(
    owner: ChatUser, stranger: ChatUser
) -> None:
    await owner.ask(str(LIBRARY_ID), "Mine")

    assert len((await owner.get("/api/v1/conversations")).json()) == 1
    assert (await stranger.get("/api/v1/conversations")).json() == []

"""Streaming a cited answer, and what happens when it goes wrong."""

from __future__ import annotations

import pytest
from chat_support import LIBRARY_ID, ChatUser, FakeGenerator, FakeRetrieval
from httpx2 import AsyncClient


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


async def test_a_stream_finishes_with_persisted_citations(user: ChatUser) -> None:
    """The plan's case: started, cited, streamed, completed - and stored."""
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

    assert events[0]["type"] == "message.started"
    assert events[-1]["type"] == "message.completed"
    message = events[-1]["message"]
    assert message["state"] == "completed"
    assert message["citations"][0]["document_version_id"]

    stored = (await user.get(f"/api/v1/conversations/{message['conversation_id']}/messages")).json()
    assistant = next(m for m in stored if m["role"] == "assistant")
    assert assistant["content"] == "Grounded answer [1]."
    assert assistant["citations"][0]["chunk_id"] == message["citations"][0]["chunk_id"]


async def test_event_ids_are_monotonic(user: ChatUser) -> None:
    """A reconnecting client can say what it already saw."""
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    ids = [event["id"] for event in events]

    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


async def test_citations_arrive_before_any_text(user: ChatUser) -> None:
    """They are known before the answer exists, because they come from retrieval."""
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    kinds = [event["type"] for event in events]

    assert kinds.index("citation") < kinds.index("message.delta")


async def test_fragments_reassemble_into_exactly_the_stored_answer(user: ChatUser) -> None:
    """The spaces between fragments have to survive the wire.

    A fragment routinely begins or ends with the space between two words.
    Losing it welds them together in the reader's copy while the stored
    answer still looks correct, so this compares the two.
    """
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    deltas = [event["text"] for event in events if event["type"] == "message.delta"]

    assert deltas == ["Grounded ", "answer [1]."]
    assert "".join(deltas) == events[-1]["message"]["content"]


async def test_an_empty_library_is_answered_without_asking_a_model(
    user: ChatUser, retrieval: FakeRetrieval, generator: FakeGenerator, control
) -> None:
    """With nothing to ground an answer in, asking a model invites invention."""
    control.generations = ()

    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

    assert events[-1]["type"] == "message.completed"
    assert "could not find anything" in events[-1]["message"]["content"]
    assert retrieval.searches == []
    assert generator.prompts == []


async def test_a_failed_generation_keeps_what_was_written(make_client) -> None:
    """The partial text is the only evidence of what went wrong."""
    failing = FakeGenerator(fragments=["Partial ", "never arrives"], fail=True)

    async with make_client(generator=failing) as http:
        user = ChatUser(http, "asker")
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
        conversations = (await user.get("/api/v1/conversations")).json()
        stored = (await user.get(f"/api/v1/conversations/{conversations[0]['id']}/messages")).json()

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "generation_failed"
    assistant = next(m for m in stored if m["role"] == "assistant")
    assert assistant["state"] == "failed"
    assert assistant["content"] == "Partial "
    assert assistant["error_code"] == "generation_failed"


async def test_an_error_event_carries_no_internals(make_client) -> None:
    """A stream is the one place an unfiltered exception reaches a user."""
    failing = FakeGenerator(fragments=["x", "y"], fail=True)

    async with make_client(generator=failing) as http:
        events = await ChatUser(http, "asker").ask(str(LIBRARY_ID), "anything")

    error = events[-1]
    assert "the endpoint went away" not in str(error)
    assert "Traceback" not in str(error)


async def test_the_model_is_given_the_retrieved_passages(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """What was retrieved is what was grounded on."""
    await user.ask(str(LIBRARY_ID), "What is the conclusion?")

    _system, prompt = generator.prompts[0]
    assert "The conclusion is well supported." in prompt
    assert "[1]" in prompt


async def test_a_conversation_is_titled_from_its_question(user: ChatUser) -> None:
    await user.ask(str(LIBRARY_ID), "What did the authors conclude about recall?")
    conversations = (await user.get("/api/v1/conversations")).json()

    assert conversations[0]["title"] == "What did the authors conclude about recall?"

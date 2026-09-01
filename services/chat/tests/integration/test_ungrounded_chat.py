"""Answering with no library attached.

Primer is usable as a chat interface on its own, and a library is something
you attach to a conversation rather than a precondition for having one.

What matters is that the two kinds of answer stay distinguishable. A cited
answer is backed by passages Primer retrieved and recorded; an ungrounded one
is not, and nothing about it may suggest otherwise.
"""

from __future__ import annotations

import pytest
from chat_support import LIBRARY_ID, ChatUser, FakeControl, FakeGenerator, FakeRetrieval
from httpx2 import AsyncClient
from primer_chat.rag import SYSTEM_PROMPT, UNGROUNDED_SYSTEM_PROMPT


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


async def test_a_question_with_no_library_is_answered(user: ChatUser) -> None:
    events = await user.ask(None, "What is a primer?")

    assert events[0]["type"] == "message.started"
    assert events[-1]["type"] == "message.completed"
    assert events[-1]["message"]["state"] == "completed"


async def test_an_ungrounded_answer_carries_no_citations(user: ChatUser) -> None:
    """The whole distinction between the two kinds of answer.

    A citation means Primer retrieved a passage and recorded it. Nothing was
    retrieved here, so an answer that arrived carrying citations would be
    claiming a provenance it does not have.
    """
    events = await user.ask(None, "What is a primer?")

    assert [event for event in events if event["type"] == "citation"] == []
    assert events[-1]["message"]["citations"] == []

    stored = (
        await user.get(f"/api/v1/conversations/{events[-1]['message']['conversation_id']}/messages")
    ).json()
    assistant = next(message for message in stored if message["role"] == "assistant")
    assert assistant["citations"] == []


async def test_nothing_is_retrieved_and_nothing_is_authorized(
    user: ChatUser, retrieval: FakeRetrieval, control: FakeControl
) -> None:
    """There is no library, so there is nothing to search and nobody to ask.

    A search with no library would be a search across everything, which is
    the one thing Retrieval's scoping exists to make impossible.
    """
    await user.ask(None, "What is a primer?")

    assert retrieval.searches == []
    assert control.asked == []


async def test_the_model_is_told_it_has_no_documents(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """A model given the grounded prompt with no passages would cite anyway."""
    await user.ask(None, "What is a primer?")

    system_prompt, user_prompt = generator.prompts[-1]
    assert system_prompt == UNGROUNDED_SYSTEM_PROMPT
    assert system_prompt != SYSTEM_PROMPT
    # The question alone: there are no passages to wrap it in.
    assert user_prompt == "What is a primer?"


async def test_asking_a_library_still_grounds_and_cites(
    user: ChatUser, generator: FakeGenerator, retrieval: FakeRetrieval
) -> None:
    """The ungrounded path must not have become the only path."""
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

    assert events[-1]["message"]["citations"] != []
    assert len(retrieval.searches) == 1
    assert generator.prompts[-1][0] == SYSTEM_PROMPT


async def test_a_conversation_keeps_the_grounding_it_started_with(
    user: ChatUser, retrieval: FakeRetrieval
) -> None:
    """The library is fixed when the thread begins.

    Otherwise a reader scrolling back through one conversation would find
    cited and uncited answers mixed together with nothing marking which was
    which.
    """
    events = await user.ask(None, "What is a primer?")
    conversation_id = events[-1]["message"]["conversation_id"]

    response = await user.follow_up(conversation_id, "And what is it for?")

    assert response.status_code == 200
    assert retrieval.searches == []

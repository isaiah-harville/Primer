"""A reasoning model's thinking, from the endpoint to the reader and back.

The splitter is unit-tested on its own. What these cover is everything
around it: that thinking leaves on its own event rather than mixed into the
answer, that it is stored so reopening a thread still shows it, and - the
one that matters most - that it never ends up in the answer text, which is
what a reader copies, exports, and cites.
"""

from __future__ import annotations

import pytest
from chat_support import ChatUser, FakeGenerator
from httpx2 import AsyncClient
from primer_chat.reasoning import Channel, Fragment

THINKING = "The question is about dosage, so the second passage is the one."
ANSWER = "The dosage was 40mg [1]."


@pytest.fixture
def owner(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "owner")


async def events_of(owner: ChatUser, question: str) -> list[dict]:
    """Asked of no library: what is under test is the model's own output."""
    return await owner.ask(None, question)


class TestAModelThatThinksAloud:
    @pytest.fixture
    def generator(self) -> FakeGenerator:
        """A model that thinks aloud, in fragments, as a real one streams."""
        return FakeGenerator(
            [
                Fragment(Channel.REASONING, THINKING),
                Fragment(Channel.ANSWER, "The dosage was "),
                Fragment(Channel.ANSWER, "40mg [1]."),
            ]
        )

    async def test_thinking_arrives_on_its_own_event(self, owner: ChatUser) -> None:
        events = await events_of(owner, "What was the dosage?")

        thinking = [event for event in events if event.get("type") == "reasoning.delta"]
        assert thinking, "no reasoning event was sent, so the rest proves nothing"
        assert "".join(event["text"] for event in thinking) == THINKING

    async def test_thinking_never_reaches_the_answer(self, owner: ChatUser) -> None:
        """The one that matters: the answer is what a reader copies and cites."""
        events = await events_of(owner, "What was the dosage?")

        answer = "".join(event["text"] for event in events if event.get("type") == "message.delta")
        assert answer == ANSWER
        assert THINKING not in answer

    async def test_the_completed_message_carries_both_apart(self, owner: ChatUser) -> None:
        events = await events_of(owner, "What was the dosage?")

        completed = next(event for event in events if event.get("type") == "message.completed")
        assert completed["message"]["content"] == ANSWER
        assert completed["message"]["reasoning"] == THINKING

    async def test_reopening_the_thread_still_shows_the_thinking(self, owner: ChatUser) -> None:
        """Stored, not merely streamed. A reader who comes back should see it."""
        events = await events_of(owner, "What was the dosage?")
        conversation_id = next(event for event in events if event.get("type") == "message.started")[
            "conversation_id"
        ]

        messages = (await owner.get(f"/api/v1/conversations/{conversation_id}/messages")).json()
        answer = next(message for message in messages if message["role"] == "assistant")

        assert answer["reasoning"] == THINKING
        assert answer["content"] == ANSWER


class TestAModelThatDoesNot:
    async def test_no_reasoning_is_recorded_as_none_rather_than_empty(
        self, owner: ChatUser
    ) -> None:
        """Most models do not think aloud, and must be told apart from one
        that does and had nothing to say."""
        events = await events_of(owner, "What did the trial establish?")

        assert not [event for event in events if event.get("type") == "reasoning.delta"]
        completed = next(event for event in events if event.get("type") == "message.completed")
        assert completed["message"]["reasoning"] is None

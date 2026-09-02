"""What the model is shown of the conversation it is continuing.

A follow-up question is usually unintelligible on its own - "and the second
one?" means nothing without the turn before it. These prove the earlier
turns reach the model, in the right order, and that the ones that should not
be replayed are not.
"""

from __future__ import annotations

import pytest
from chat_support import LIBRARY_ID, ChatUser, FakeGenerator, parse_events
from httpx2 import AsyncClient
from primer_chat.config import Settings

ANSWER = "Grounded answer [1]."


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


async def test_the_opening_question_has_nothing_behind_it(
    user: ChatUser, generator: FakeGenerator
) -> None:
    await user.ask(str(LIBRARY_ID), "What is the conclusion?")

    assert generator.histories == [()]


async def test_a_follow_up_shows_the_model_the_turns_before_it(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """The bug this file exists for: without this the model saw one question.

    The assertion is on what reached the generator rather than on the answer,
    because a fake model will happily produce a coherent-looking reply to a
    question it was shown no context for.
    """
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    conversation_id = events[0]["conversation_id"]

    await user.follow_up(conversation_id, "And what about the second one?")

    assert generator.histories[1] == (
        ("user", "What is the conclusion?"),
        ("assistant", ANSWER),
    )


async def test_the_question_being_asked_is_not_also_in_the_history(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """History is read before this turn's own messages are written."""
    events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
    conversation_id = events[0]["conversation_id"]

    await user.follow_up(conversation_id, "And the second?")

    assert "And the second?" not in [content for _, content in generator.histories[1]]


async def test_a_question_comes_before_its_answer(user: ChatUser) -> None:
    """Both are written in one transaction, so both carry the same timestamp.

    Ordering them by `created_at` therefore fell through to comparing random
    UUIDs, which put the answer first about half the time. Repeated because a
    coin lands on the right side often enough to pass once.
    """
    for _ in range(6):
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
        conversation_id = events[0]["conversation_id"]
        stored = (await user.get(f"/api/v1/conversations/{conversation_id}/messages")).json()

        assert [message["role"] for message in stored] == ["user", "assistant"]


async def test_an_answer_that_failed_partway_is_not_replayed(
    make_client, generator: FakeGenerator
) -> None:
    """A fragment that stops mid-sentence is evidence, not an example.

    The question that provoked it is still replayed: it was asked, and the
    next question probably follows from it.
    """
    async with make_client(generator=FakeGenerator(fail=True)) as broken:
        events = parse_events(
            (
                await ChatUser(broken, "asker").post_ask("What is the conclusion?", str(LIBRARY_ID))
            ).text
        )
    conversation_id = events[0]["conversation_id"]

    async with make_client(generator=generator) as working:
        await ChatUser(working, "asker").follow_up(conversation_id, "Try again?")

    assert generator.histories[0] == (("user", "What is the conclusion?"),)


class TestABoundedHistory:
    @pytest.fixture
    def settings(self) -> Settings:
        """Two messages: one exchange, so the turn before last falls off."""
        return Settings(auth_mode="oidc", chat_history_messages=2)

    async def test_only_the_most_recent_messages_are_replayed(
        self, user: ChatUser, generator: FakeGenerator
    ) -> None:
        """The oldest go first. A long conversation is understood from its end."""
        events = await user.ask(str(LIBRARY_ID), "First question?")
        conversation_id = events[0]["conversation_id"]
        await user.follow_up(conversation_id, "Second question?")
        await user.follow_up(conversation_id, "Third question?")

        assert generator.histories[2] == (("user", "Second question?"), ("assistant", ANSWER))


class TestHistoryTurnedOff:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(auth_mode="oidc", chat_history_messages=0)

    async def test_each_question_is_answered_alone(
        self, user: ChatUser, generator: FakeGenerator
    ) -> None:
        """Zero is a supported deployment, not a broken one."""
        events = await user.ask(str(LIBRARY_ID), "First question?")
        await user.follow_up(events[0]["conversation_id"], "Second question?")

        assert generator.histories == [(), ()]

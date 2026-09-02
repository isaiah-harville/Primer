"""Fitting a turn into the window the model has.

The window is the constraint everything else in a prompt competes for, and
Primer cannot measure a prompt exactly - it talks to endpoints whose
tokenizers it does not hold. These prove the parts that must be true anyway:
that what is cut is cut in the right order, that the reader is never shown a
source the model was not, and that running out of room is said out loud
rather than dressed up as an empty library.
"""

from __future__ import annotations

import re

import pytest
from chat_support import LIBRARY_ID, ChatUser, FakeGenerator, FakeRetrieval
from httpx2 import AsyncClient
from primer_chat.config import Settings

#: Long enough that a handful of them cannot share a small window.
PASSAGE = "The measured result was unambiguous in every replication. " * 12


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


class TestASmallWindow:
    @pytest.fixture
    def settings(self) -> Settings:
        """Small enough to force choices, large enough to answer at all."""
        return Settings(auth_mode="oidc", chat_context_tokens=1024, chat_reply_tokens=64)

    @pytest.fixture
    def retrieval(self) -> FakeRetrieval:
        return FakeRetrieval([f"{index}. {PASSAGE}" for index in range(8)])

    async def test_the_reader_is_shown_exactly_what_the_model_was(
        self, user: ChatUser, generator: FakeGenerator
    ) -> None:
        """The citations and the passages are one claim, so they are cut together.

        This is the whole reason the trim happens before the citation events
        are sent. A citation says the answer was written from this document;
        emitting one for a passage that then did not fit would put a source
        in front of the reader that the model never read.
        """
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

        cited = [event for event in events if event["type"] == "citation"]
        _, prompt = generator.prompts[0]
        shown = re.findall(r"^\[(\d+)\] ", prompt, flags=re.MULTILINE)

        assert len(cited) == len(shown)
        assert [event["index"] for event in cited] == [int(number) for number in shown]

    async def test_more_was_retrieved_than_was_used(
        self, user: ChatUser, generator: FakeGenerator, retrieval: FakeRetrieval
    ) -> None:
        """Otherwise the test above passes without anything being trimmed."""
        await user.ask(str(LIBRARY_ID), "What is the conclusion?")

        _, prompt = generator.prompts[0]
        shown = re.findall(r"^\[(\d+)\] ", prompt, flags=re.MULTILINE)

        assert 0 < len(shown) < len(retrieval.contents)

    async def test_the_passages_win_the_room_and_the_history_gives_way(
        self, user: ChatUser, generator: FakeGenerator
    ) -> None:
        """An answer without its sources is a different kind of answer.

        The earlier turns are what a small window costs, and the question
        being asked now is what it is spent on.
        """
        opening = "What is the conclusion, and how was it arrived at? " * 24
        events = await user.ask(str(LIBRARY_ID), opening)
        conversation_id = events[0]["conversation_id"]

        await user.follow_up(conversation_id, "And the second?")

        _, prompt = generator.prompts[1]
        assert re.search(r"^\[1\] ", prompt, flags=re.MULTILINE)
        assert generator.histories[1] == ()


class TestAWindowNothingFitsIn:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(auth_mode="oidc", chat_context_tokens=1024, chat_reply_tokens=64)

    @pytest.fixture
    def retrieval(self) -> FakeRetrieval:
        return FakeRetrieval(["Every word of a very long document. " * 2000])

    async def test_running_out_of_room_is_not_reported_as_an_empty_library(
        self, user: ChatUser, generator: FakeGenerator
    ) -> None:
        """ "I found nothing" would send someone looking for a document that is there."""
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

        assert events[-1]["type"] == "error"
        assert events[-1]["code"] == "context_exhausted"
        assert generator.prompts == []

    async def test_no_source_is_shown_for_an_answer_that_was_never_written(
        self, user: ChatUser
    ) -> None:
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")

        assert [event for event in events if event["type"] == "citation"] == []

    async def test_the_failure_is_recorded_against_the_message(self, user: ChatUser) -> None:
        events = await user.ask(str(LIBRARY_ID), "What is the conclusion?")
        conversation_id = events[0]["conversation_id"]

        stored = (await user.get(f"/api/v1/conversations/{conversation_id}/messages")).json()
        answer = next(message for message in stored if message["role"] == "assistant")

        assert answer["state"] == "failed"
        assert answer["error_code"] == "context_exhausted"


class TestAModelWithItsOwnWindow:
    @pytest.fixture
    def settings(self) -> Settings:
        """A deployment offering two models whose windows differ."""
        return Settings(
            auth_mode="oidc",
            chat_model="small-model",
            chat_models=("large-model",),
            chat_context_tokens=1024,
            chat_reply_tokens=64,
            chat_model_context_tokens={"large-model": 200_000},
        )

    @pytest.fixture
    def retrieval(self) -> FakeRetrieval:
        return FakeRetrieval([f"{index}. {PASSAGE}" for index in range(8)])

    async def test_the_window_follows_the_model_that_was_chosen(
        self, user: ChatUser, generator: FakeGenerator, retrieval: FakeRetrieval
    ) -> None:
        """The same question, two models, two amounts of room."""
        await user.ask(str(LIBRARY_ID), "What is the conclusion?")
        await user.ask(str(LIBRARY_ID), "What is the conclusion?", model="large-model")

        counts = [
            len(re.findall(r"^\[(\d+)\] ", prompt, flags=re.MULTILINE))
            for _, prompt in generator.prompts
        ]

        assert counts[0] < counts[1] == len(retrieval.contents)

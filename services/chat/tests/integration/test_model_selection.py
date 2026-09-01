"""Choosing which model answers.

A deployment may serve several. Which one wrote an answer is part of the
answer, so it is recorded on the message rather than assumed from
configuration that may since have changed.
"""

from __future__ import annotations

import pytest
from chat_support import ChatUser, FakeGenerator
from httpx2 import AsyncClient
from primer_chat.config import Settings

MODELS = ("primary-model", "second-model")


@pytest.fixture
def settings() -> Settings:
    """A deployment offering two models. Overrides the suite's default."""
    return Settings(auth_mode="oidc", chat_model=MODELS[0], chat_models=(MODELS[1],))


@pytest.fixture
def user(client: AsyncClient) -> ChatUser:
    return ChatUser(client, "asker")


async def test_the_offered_models_are_listed_with_the_default_first(user: ChatUser) -> None:
    body = (await user.get("/api/v1/models")).json()

    assert [entry["id"] for entry in body["models"]] == list(MODELS)
    assert [entry["default"] for entry in body["models"]] == [True, False]


async def test_a_request_with_no_preference_uses_the_default(
    user: ChatUser, generator: FakeGenerator
) -> None:
    events = await user.ask(None, "What is a primer?")

    assert generator.models == [MODELS[0]]
    assert events[-1]["message"]["provider_model"] == MODELS[0]


async def test_a_chosen_model_reaches_the_provider_and_is_recorded(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """Recorded, because an answer's provenance includes what wrote it."""
    events = await user.ask(None, "What is a primer?", model=MODELS[1])

    assert generator.models == [MODELS[1]]
    assert events[-1]["message"]["provider_model"] == MODELS[1]


async def test_a_model_this_deployment_does_not_offer_is_refused(
    user: ChatUser, generator: FakeGenerator
) -> None:
    """Refused, not quietly swapped for the default.

    An endpoint serves models an operator never chose to expose here, and
    answering from one of them anyway would both bypass that choice and
    record a model the user did not pick.
    """
    response = await user.post_ask("Anything", model="some-other-model")

    assert response.status_code == 422
    assert "some-other-model" in response.text
    assert generator.models == []

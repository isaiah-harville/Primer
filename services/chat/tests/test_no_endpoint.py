"""A question is never sent somewhere nobody configured.

The OpenAI client reads a null base URL as its own hosted API. Primer is
self-hosted and its prompts carry passages retrieved from a user's private
documents, so a deployment that has simply not been pointed anywhere must
fail loudly rather than quietly send those passages to a third party.

That state became reachable when the chart's model stopped being required:
before, a deployment could not start without naming an endpoint.
"""

from __future__ import annotations

import pytest
from primer_chat.config import Settings
from primer_chat.generation import Endpoint, HaystackChatGenerator, NoEndpoint

#: Where a null base URL silently resolves to, which is the whole hazard.
SOMEBODY_ELSES_API = "api.openai.com"


def generator(**settings: object) -> HaystackChatGenerator:
    return HaystackChatGenerator(Settings(**settings))  # ty: ignore[invalid-argument-type]


def test_no_endpoint_anywhere_is_refused() -> None:
    """The regression. A client built here would have gone to OpenAI."""
    with pytest.raises(NoEndpoint):
        generator(chat_model="some-model")._for("some-model")


def test_an_empty_endpoint_is_refused_too() -> None:
    """An unset environment variable arrives as an empty string, not None."""
    with pytest.raises(NoEndpoint):
        generator(chat_model="some-model")._for("some-model", Endpoint(base_url=""))


def test_no_model_anywhere_is_refused() -> None:
    """Reachable since the chart's model became optional."""
    with pytest.raises(NoEndpoint):
        generator(chat_base_url="http://local:8000/v1")._for(None)


def test_a_configured_endpoint_is_used_as_given() -> None:
    """The ordinary case still works, and goes where it was told."""
    client = generator(chat_model="m", chat_base_url="http://local:8000/v1")._for("m")

    assert SOMEBODY_ELSES_API not in str(client.api_base_url)
    assert "local:8000" in str(client.api_base_url)


def test_a_provider_endpoint_overrides_the_deployment_s_own() -> None:
    """Choosing a provider is what sends a question somewhere else."""
    built = generator(chat_model="m", chat_base_url="http://local:8000/v1")
    client = built._for("m", Endpoint(base_url="http://elsewhere:9000/v1", api_key="k"))

    assert "elsewhere:9000" in str(client.api_base_url)


def test_two_providers_serving_one_model_get_separate_clients() -> None:
    """Keyed on the endpoint as well as the name.

    Keying on the model alone would send every question to whichever
    endpoint was asked first, and keep doing so after an administrator
    changed the other one.
    """
    built = generator(chat_model="shared", chat_base_url="http://a:8000/v1")
    first = built._for("shared", Endpoint(base_url="http://a:8000/v1"))
    second = built._for("shared", Endpoint(base_url="http://b:8000/v1"))

    assert first is not second
    assert "a:8000" in str(first.api_base_url)
    assert "b:8000" in str(second.api_base_url)

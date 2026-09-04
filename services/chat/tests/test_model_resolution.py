"""Which model answers, when the request names one and when it does not.

The picker sends the model it is showing, so nearly every question names
one. What this pins down is the other path - and the empty string, which is
what an unset environment variable actually is.

A deployment that configures no model is supposed to resolve one from the
catalog: it asks the providers what they serve and uses the one it would
have shown as the default. `PRIMER_CHAT_MODEL` exists to say which to prefer,
not to make the deployment work at all.
"""

from __future__ import annotations

import pytest
from primer_chat.config import Settings


def settings(**overrides: object) -> Settings:
    return Settings(chat_base_url="http://endpoint:8000/v1", **overrides)  # ty: ignore[invalid-argument-type]


def test_the_requested_model_wins() -> None:
    """Picking from the list is the whole point of the picker."""
    assert settings(chat_model="configured").resolve_model("picked") == "picked"


def test_the_configured_model_is_the_fallback() -> None:
    assert settings(chat_model="configured").resolve_model(None) == "configured"


def test_nothing_configured_resolves_to_nothing() -> None:
    """None is what sends the caller to the catalog for a default."""
    assert settings().resolve_model(None) is None


@pytest.mark.parametrize("unset", ["", None])
def test_an_unset_model_is_not_a_model_named_empty(unset: str | None) -> None:
    """The regression, and it cost a 404 on every question.

    An unset environment variable arrives as an empty string, and an empty
    string passed the caller's `is not None` check as though a model had been
    named. It was sent to the endpoint, which replied `Model '' not found` -
    so a deployment that deliberately configured no model looked broken, and
    the apparent fix was to configure one.
    """
    assert settings(chat_model=unset).resolve_model(None) is None


def test_an_empty_request_falls_back_rather_than_asking_for_nothing() -> None:
    """A client sending `model: ""` must not blank a configured default."""
    assert settings(chat_model="configured").resolve_model("") == "configured"

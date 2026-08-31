"""Provider configuration, and the capabilities it is allowed to claim.

The rule these enforce is that a capability is declared, never inferred.
Guessing from a model name produces a deployment that offers tool use and
then fails the moment a user tries it.
"""

from __future__ import annotations

import pytest
from primer_chat.provider_diagnostics import DeploymentCapabilities, ProviderDiagnostics
from primer_chat.providers import ProviderProfile, ProviderTarget
from pydantic import SecretStr, ValidationError


def target(
    base_url: str = "http://model:8000/v1",
    model: str = "local-model",
    max_context_tokens: int = 8192,
    api_key: SecretStr | None = None,
    supports_tools: bool = False,
) -> ProviderTarget:
    """Spelled out rather than **kwargs, so the fields stay type-checked."""
    return ProviderTarget(
        base_url=base_url,
        model=model,
        max_context_tokens=max_context_tokens,
        api_key=api_key,
        supports_tools=supports_tools,
    )


def test_tool_capability_is_never_inferred_from_model_name() -> None:
    """The plan's case: a suggestive name grants nothing."""
    profile = ProviderProfile(chat=target(model="toolish-name", supports_tools=False))
    assert ProviderDiagnostics(profile).declared_tools is False


def test_a_dull_name_can_still_declare_tools() -> None:
    """The inverse matters too: the operator decides, not the string."""
    profile = ProviderProfile(chat=target(model="m1", supports_tools=True))
    assert ProviderDiagnostics(profile).declared_tools is True


def test_a_context_window_must_be_stated() -> None:
    """A window Primer does not know is one it will overrun silently."""
    with pytest.raises(ValidationError):
        ProviderTarget(base_url="http://model/v1", model="m")  # ty: ignore[missing-argument]


def test_base_urls_keep_their_provider_specific_path() -> None:
    """Ollama and llama.cpp serve at /v1; rewriting paths breaks correct URLs."""
    assert target(base_url="http://ollama:11434/v1/").base_url == "http://ollama:11434/v1"
    assert target(base_url="http://gw/openai/v1").base_url == "http://gw/openai/v1"


def test_an_empty_base_url_is_refused() -> None:
    with pytest.raises(ValidationError):
        target(base_url="   ")


def test_api_keys_stay_secret() -> None:
    """A key must not appear in a log line or a repr."""
    value = "sk-real-secret"
    configured = target(api_key=SecretStr(value))
    assert value not in repr(configured)
    assert configured.secret == value


def test_a_missing_key_still_sends_a_placeholder() -> None:
    """Many local servers ignore the value but require the header."""
    placeholder = "none"
    assert target(api_key=None).secret == placeholder


def test_settings_are_immutable() -> None:
    """A profile changing under a running request would be untraceable."""
    with pytest.raises(ValidationError):
        target().model = "swapped"  # ty: ignore[invalid-assignment]


def test_unknown_settings_are_refused() -> None:
    """A typo must fail loudly rather than silently keeping a default."""
    with pytest.raises(ValidationError):
        ProviderTarget(
            base_url="http://model/v1",
            model="m",
            max_context_tokens=1,
            supports_toolz=True,  # ty: ignore[unknown-argument]
        )


def test_ingestion_depends_on_embeddings_not_on_chat() -> None:
    """Without embeddings nothing can be indexed, so nothing can be asked."""
    assert DeploymentCapabilities(chat=True, embeddings=False, tools=True).can_ingest is False
    assert DeploymentCapabilities(chat=False, embeddings=True, tools=False).can_ingest is True

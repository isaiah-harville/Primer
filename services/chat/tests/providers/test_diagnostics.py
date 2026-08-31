"""Probing a provider, and what each kind of failure costs.

Embeddings are load-bearing and tools are not, so the two failures are
deliberately not equivalent: one makes the deployment unable to ingest, the
other removes one optional feature.
"""

from __future__ import annotations

import pytest
from primer_chat.provider_diagnostics import ProviderDiagnostics
from primer_chat.providers import ProviderProfile, ProviderTarget
from provider_stub import StubProvider


def target(
    port: int, *, supports_tools: bool = False, model: str = "local-model"
) -> ProviderTarget:
    return ProviderTarget(
        base_url=f"http://127.0.0.1:{port}/v1",
        model=model,
        max_context_tokens=8192,
        timeout_seconds=2.0,
        supports_tools=supports_tools,
    )


async def test_a_reachable_endpoint_serving_the_model_passes() -> None:
    async with StubProvider(models=["local-model"]) as stub:
        profile = ProviderProfile(chat=target(stub.port), embeddings=target(stub.port))
        diagnostics = ProviderDiagnostics(profile)

        assert (await diagnostics.check_chat()).ok
        assert (await diagnostics.check_embeddings()).ok


async def test_an_unreachable_endpoint_is_reported_not_raised(unused_port: int) -> None:
    """An operator needs a code, not a traceback."""
    profile = ProviderProfile(chat=target(unused_port))
    result = await ProviderDiagnostics(profile).check_chat()

    assert result.ok is False
    assert result.code == "provider_unreachable"


async def test_a_refusing_endpoint_is_distinguished_from_an_absent_one() -> None:
    """Wrong credentials and wrong address are different problems."""
    async with StubProvider(status=401) as stub:
        result = await ProviderDiagnostics(ProviderProfile(chat=target(stub.port))).check_chat()

    assert result.ok is False
    assert result.code == "provider_refused"


async def test_an_unlisted_model_is_a_warning_not_a_failure() -> None:
    """Gateways routinely serve models they do not list."""
    async with StubProvider(models=["something-else"]) as stub:
        result = await ProviderDiagnostics(ProviderProfile(chat=target(stub.port))).check_chat()

    assert result.ok is True
    assert result.code == "model_not_listed"


async def test_no_embedding_endpoint_means_nothing_can_be_ingested() -> None:
    async with StubProvider(models=["local-model"]) as stub:
        profile = ProviderProfile(chat=target(stub.port), embeddings=None)
        result = await ProviderDiagnostics(profile).check_embeddings()

    assert result.ok is False
    assert result.code == "embeddings_unconfigured"


async def test_undeclared_tools_are_not_probed() -> None:
    """An operator who has not declared tool use has not consented to it.

    A lucky probe would enable a feature they did not choose, so the
    declaration gates the check rather than the other way round.
    """
    async with StubProvider(models=["local-model"]) as stub:
        profile = ProviderProfile(chat=target(stub.port, supports_tools=False))
        result = await ProviderDiagnostics(profile).check_tools()

    assert result.ok is False
    assert result.code == "tools_not_declared"
    assert stub.requests == 0


async def test_declared_tools_are_verified_against_the_endpoint() -> None:
    async with StubProvider(models=["local-model"]) as stub:
        profile = ProviderProfile(chat=target(stub.port, supports_tools=True))
        result = await ProviderDiagnostics(profile).check_tools()

    assert result.ok is True


async def test_capabilities_report_each_role_separately() -> None:
    """A deployment can chat but not embed, and must say so."""
    async with StubProvider(models=["local-model"]) as stub:
        profile = ProviderProfile(chat=target(stub.port, supports_tools=True), embeddings=None)
        capabilities = await ProviderDiagnostics(profile).capabilities()

    assert capabilities.chat is True
    assert capabilities.tools is True
    assert capabilities.embeddings is False
    assert capabilities.can_ingest is False


@pytest.fixture
def unused_port() -> int:
    """A port nothing is listening on, for the unreachable case."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])

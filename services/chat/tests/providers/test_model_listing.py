"""What the model list says when the inference endpoint is not there.

The failure this guards against is a quiet one. Primer used to answer an
unreachable endpoint with the name of its configured default, so the picker
showed a model, the deployment looked healthy, and the first sign of trouble
was a question that hung and then failed. An operator reading the screen had
been told the opposite of the truth.

A real socket rather than a patched client, for the same reason the
diagnostics use one: "unreachable" and "answered badly" are different states
and only a real connection tells them apart.
"""

from __future__ import annotations

from primer_chat.config import Settings
from primer_chat.routes import _discover_models
from provider_stub import StubProvider


def settings_for(port: int | None, *, model: str = "configured-default") -> Settings:
    return Settings(
        chat_base_url=f"http://127.0.0.1:{port}/v1" if port else None,
        chat_model=model,
    )


async def test_a_reachable_endpoint_offers_what_it_serves() -> None:
    async with StubProvider(models=["configured-default", "another"]) as stub:
        listed = await _discover_models(settings_for(stub.port))

    assert listed.endpoint_reachable
    assert [model.id for model in listed.models] == ["configured-default", "another"]
    assert [model.id for model in listed.models if model.default] == ["configured-default"]


async def test_an_unreachable_endpoint_offers_nothing_and_says_so() -> None:
    """The regression: no phantom model, and a reason a person can act on."""
    # A port nothing is listening on: the stub is started and stopped so the
    # port is real and certainly closed, rather than guessed at.
    async with StubProvider() as stub:
        port = stub.port

    listed = await _discover_models(settings_for(port))

    assert listed.models == ()
    assert not listed.endpoint_reachable
    assert listed.detail is not None
    assert str(port) in listed.detail


async def test_an_unconfigured_endpoint_offers_nothing_and_says_so() -> None:
    listed = await _discover_models(settings_for(None))

    assert listed.models == ()
    assert not listed.endpoint_reachable
    assert listed.detail is not None


async def test_an_endpoint_serving_nothing_is_not_the_same_as_an_absent_one() -> None:
    """Up with no model loaded is a different problem, and a different fix."""
    async with StubProvider(models=[]) as stub:
        listed = await _discover_models(settings_for(stub.port))

    assert listed.models == ()
    assert listed.endpoint_reachable
    assert listed.detail is not None


async def test_a_default_the_endpoint_does_not_serve_is_not_offered() -> None:
    """A configured default naming a removed model is the same lie, smaller.

    The deployment's chosen default is gone, so something it does serve
    becomes the default rather than a name nothing answers to.
    """
    async with StubProvider(models=["actually-served"]) as stub:
        listed = await _discover_models(settings_for(stub.port, model="removed-model"))

    assert [model.id for model in listed.models] == ["actually-served"]
    assert [model.id for model in listed.models if model.default] == ["actually-served"]

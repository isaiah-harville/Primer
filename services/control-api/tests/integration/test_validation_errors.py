"""A rejected request answers in the shape Primer promises.

Validation is the one failure the framework catches before any of Primer's
code runs, so it was the one that answered in FastAPI's shape instead of the
contract's: a list of objects under `detail`, where every client reads a
string. The web app rendered that as "[object Object]", which tells a user
nothing and reads as a broken application rather than a rejected field.
"""

from __future__ import annotations

from control_support import UserClient

#: One character past the contract's limit for a library name.
TOO_LONG = "x" * 121


async def test_a_rejected_field_is_described_in_words(owner: UserClient) -> None:
    """The regression. `detail` is a sentence, not a structure."""
    response = await owner.post("/api/v1/libraries", {"name": TOO_LONG})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "120" in detail, "the reason should say what the limit actually is"


async def test_a_rejected_request_carries_the_contract_s_fields(owner: UserClient) -> None:
    """A client branching on `code` must be able to, here as anywhere else."""
    body = (await owner.post("/api/v1/libraries", {"name": TOO_LONG})).json()

    assert body["code"] == "validation_failed"
    assert body["status"] == 422
    assert body["title"]


async def test_the_rejected_value_is_not_echoed_back(owner: UserClient) -> None:
    """It is already on the user's screen, and it is the unbounded part.

    FastAPI's own body includes the input that failed. Repeating a rejected
    field back into an error message is how an error message becomes an
    injection surface for whoever reads it next.
    """
    body = (await owner.post("/api/v1/libraries", {"name": TOO_LONG})).json()

    assert TOO_LONG not in str(body)


async def test_the_field_that_was_rejected_is_named(owner: UserClient) -> None:
    """With several fields, "invalid" alone leaves a user guessing which."""
    body = (await owner.post("/api/v1/libraries", {"name": TOO_LONG})).json()

    assert "name" in body["detail"]


async def test_a_missing_field_is_rejected_the_same_way(owner: UserClient) -> None:
    body = (await owner.post("/api/v1/libraries", {})).json()

    assert body["code"] == "validation_failed"
    assert isinstance(body["detail"], str)

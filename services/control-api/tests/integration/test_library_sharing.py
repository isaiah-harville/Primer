"""Owner-managed library sharing, and the isolation it must not break.

Sharing is the first thing in Primer that lets one person read another
person's material, so most of this file is about what a share does *not*
grant. A grant that quietly carried the ability to rename, upload to, or
re-share a library would be a much larger decision than the owner made.

Everything here drives the real boundary: identity arrives in the header
the edge injects, and authorization is whatever `LibraryAccess` decides
against real rows in real PostgreSQL.
"""

from __future__ import annotations

from typing import Any

import pytest
from control_support import UserClient
from httpx2 import AsyncClient

COLLEAGUE_EMAIL = "colleague@example.edu"
OWNER_EMAIL = "owner@example.edu"

#: The cluster-internal credential the conftest configures. Chat presents
#: this when it asks Control what a person may read.
SERVICE_TOKEN = "test-service-token"  # noqa: S105


async def create_library(user: UserClient, name: str = "Shared sources") -> dict[str, Any]:
    response = await user.post("/api/v1/libraries", {"name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def register(user: UserClient) -> str:
    """Make a user known to Primer, and return their id.

    A user row is written when an identity first acts, so somebody who has
    only ever read cannot be shared with. Creating a library is the cheapest
    way to become real.
    """
    library = await create_library(user, "Their own")
    return str(library["owner_user_id"])


async def share(owner: UserClient, library_id: str, email: str) -> Any:
    return await owner.post(f"/api/v1/libraries/{library_id}/shares", {"email": email})


async def library_scope(http: AsyncClient, library_id: str, user_id: str) -> Any:
    """Ask Control what a principal may read, the way Chat does.

    This is the seam that decides whether a question is answered at all: a
    library the principal cannot read is 404 here, and nothing reaches
    Retrieval or a model.
    """
    return await http.post(
        "/internal/v1/authz/library-scope",
        json={
            "principal": {"subject": "chat-on-behalf", "user_id": user_id, "groups": []},
            "library_id": library_id,
        },
        headers={"X-Primer-Service-Token": SERVICE_TOKEN},
    )


async def test_a_shared_library_becomes_readable(owner: UserClient, colleague: UserClient) -> None:
    """The point of the feature, stated once."""
    await register(colleague)
    library = await create_library(owner)
    assert (await colleague.get(f"/api/v1/libraries/{library['id']}")).status_code == 404

    assert (await share(owner, library["id"], COLLEAGUE_EMAIL)).status_code == 201

    read = await colleague.get(f"/api/v1/libraries/{library['id']}")
    assert read.status_code == 200
    assert read.json()["name"] == "Shared sources"


async def test_a_shared_library_is_listed_once(owner: UserClient, colleague: UserClient) -> None:
    """Not once per grant.

    `readable` is dropped into a `where` clause over `libraries`; expressed
    as a join it would multiply the rows by the number of people the library
    is shared with, and the same library would appear several times in one
    sidebar.
    """
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    listed = (await colleague.get("/api/v1/libraries")).json()
    shared = [entry for entry in listed if entry["id"] == library["id"]]
    assert len(shared) == 1


async def test_the_owner_is_still_named_on_a_shared_library(
    owner: UserClient, colleague: UserClient
) -> None:
    """So the interface can tell a library of yours from one lent to you."""
    colleague_id = await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    seen = (await colleague.get(f"/api/v1/libraries/{library['id']}")).json()
    assert seen["owner_user_id"] == library["owner_user_id"]
    assert seen["owner_user_id"] != colleague_id


async def test_sharing_does_not_grant_renaming(owner: UserClient, colleague: UserClient) -> None:
    """Reading is the whole grant.

    Renaming, deleting and uploading stay with the owner, because a share
    says nothing about them. Roles are a separate design; until there is
    one, the honest reading of "shared" is "may read".
    """
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    renamed = await colleague.patch(f"/api/v1/libraries/{library['id']}", {"name": "Mine now"})
    assert renamed.status_code == 404


async def test_sharing_does_not_grant_deleting(owner: UserClient, colleague: UserClient) -> None:
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    assert (await colleague.delete(f"/api/v1/libraries/{library['id']}")).status_code == 404
    # And the owner still has it.
    assert (await owner.get(f"/api/v1/libraries/{library['id']}")).status_code == 200


async def test_sharing_does_not_grant_uploading(owner: UserClient, colleague: UserClient) -> None:
    """A shared library is not a shared drive."""
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    uploaded = await colleague.upload(library["id"], "theirs.md", b"# Not yours to add")
    assert uploaded.status_code == 404


async def test_sharing_does_not_grant_sharing_onward(
    owner: UserClient, colleague: UserClient, stranger: UserClient
) -> None:
    """Only the owner decides who else sees it.

    Otherwise one grant becomes an unbounded number of them, and the owner
    has no way to know who holds their material.
    """
    await register(colleague)
    await register(stranger)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    passed_on = await colleague.post(
        f"/api/v1/libraries/{library['id']}/shares", {"email": "stranger@example.edu"}
    )
    assert passed_on.status_code == 404


async def test_sharing_does_not_reveal_who_else_holds_it(
    owner: UserClient, colleague: UserClient
) -> None:
    """The list of people trusted with a private library is the owner's."""
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    assert (await colleague.get(f"/api/v1/libraries/{library['id']}/shares")).status_code == 404
    assert (await owner.get(f"/api/v1/libraries/{library['id']}/shares")).status_code == 200


async def test_revoking_blocks_reading_immediately(
    owner: UserClient, colleague: UserClient
) -> None:
    """The acceptance criterion, and the reason grants are read per request.

    Nothing is cached and nothing is copied, so the next request is already
    refused - there is no window and no cleanup to wait for.
    """
    colleague_id = await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)
    assert (await colleague.get(f"/api/v1/libraries/{library['id']}")).status_code == 200

    revoked = await owner.delete(f"/api/v1/libraries/{library['id']}/shares/{colleague_id}")
    assert revoked.status_code == 204

    assert (await colleague.get(f"/api/v1/libraries/{library['id']}")).status_code == 404
    assert (await colleague.get("/api/v1/libraries")).json() == [
        entry
        for entry in (await colleague.get("/api/v1/libraries")).json()
        if entry["id"] != library["id"]
    ]


async def test_revoking_blocks_being_answered_from(
    owner: UserClient, colleague: UserClient, client: AsyncClient
) -> None:
    """The seam Chat asks, rather than the one a browser asks.

    A revocation that stopped the library appearing in a list but still
    answered questions about it would be the worst version of this bug: the
    owner would believe access was withdrawn and it would not be.
    """
    colleague_id = await register(colleague)
    library = await create_library(owner)

    assert (await library_scope(client, library["id"], colleague_id)).status_code == 404
    await share(owner, library["id"], COLLEAGUE_EMAIL)
    assert (await library_scope(client, library["id"], colleague_id)).status_code == 200

    await owner.delete(f"/api/v1/libraries/{library['id']}/shares/{colleague_id}")
    assert (await library_scope(client, library["id"], colleague_id)).status_code == 404


async def test_a_shared_library_can_be_shared_again_after_revoking(
    owner: UserClient, colleague: UserClient
) -> None:
    """Which is why the uniqueness constraint is partial.

    A revoked grant is kept as a record, so a plain constraint over the pair
    would refuse to give access back to someone it had been taken from.
    """
    colleague_id = await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)
    await owner.delete(f"/api/v1/libraries/{library['id']}/shares/{colleague_id}")

    again = await share(owner, library["id"], COLLEAGUE_EMAIL)
    assert again.status_code == 201, again.text
    assert (await colleague.get(f"/api/v1/libraries/{library['id']}")).status_code == 200


async def test_sharing_twice_is_not_an_error(owner: UserClient, colleague: UserClient) -> None:
    """A double-clicked button is not a failure.

    The question being asked is "may this person read it", and the answer
    after two identical requests is the answer after one.
    """
    await register(colleague)
    library = await create_library(owner)

    first = await share(owner, library["id"], COLLEAGUE_EMAIL)
    second = await share(owner, library["id"], COLLEAGUE_EMAIL)

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["user_id"] == second.json()["user_id"]
    assert len((await owner.get(f"/api/v1/libraries/{library['id']}/shares")).json()) == 1


async def test_revoking_a_share_that_is_not_there(owner: UserClient, colleague: UserClient) -> None:
    """Nothing to revoke reads as nothing to find, like every other delete."""
    colleague_id = await register(colleague)
    library = await create_library(owner)

    gone = await owner.delete(f"/api/v1/libraries/{library['id']}/shares/{colleague_id}")
    assert gone.status_code == 404


async def test_sharing_with_someone_who_has_never_signed_in(owner: UserClient) -> None:
    """Said plainly, because the fix is for them to sign in once.

    A silent success would leave the owner believing they had shared
    something with a colleague who could not see it.
    """
    library = await create_library(owner)
    response = await share(owner, library["id"], "nobody@example.edu")

    assert response.status_code == 404
    assert "sign in" in response.json()["detail"]


async def test_sharing_with_yourself_is_refused(owner: UserClient) -> None:
    """It would be a row that grants what the owner already has."""
    library = await create_library(owner)

    response = await share(owner, library["id"], OWNER_EMAIL)
    assert response.status_code == 422


async def test_an_address_is_matched_whatever_case_it_is_typed(
    owner: UserClient, colleague: UserClient
) -> None:
    """People hand addresses round in whatever case they please."""
    await register(colleague)
    library = await create_library(owner)

    response = await share(owner, library["id"], "Colleague@Example.EDU")
    assert response.status_code == 201, response.text


async def test_a_stranger_cannot_share_a_library_they_cannot_see(
    owner: UserClient, stranger: UserClient, colleague: UserClient
) -> None:
    """And is told the library does not exist, not that it is not theirs."""
    await register(colleague)
    library = await create_library(owner)

    response = await share(stranger, library["id"], COLLEAGUE_EMAIL)
    assert response.status_code == 404
    assert len((await owner.get(f"/api/v1/libraries/{library['id']}/shares")).json()) == 0


async def test_the_share_list_names_the_person(owner: UserClient, colleague: UserClient) -> None:
    """An id is not something an owner can check their intention against."""
    colleague_id = await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)

    shares = (await owner.get(f"/api/v1/libraries/{library['id']}/shares")).json()
    assert len(shares) == 1
    assert shares[0]["user_id"] == colleague_id
    assert shares[0]["email"] == COLLEAGUE_EMAIL


@pytest.mark.parametrize("path", ["", "/documents"])
async def test_deleting_a_library_ends_the_sharing_of_it(
    owner: UserClient, colleague: UserClient, path: str
) -> None:
    """A tombstoned library is gone for everyone, not only its owner."""
    await register(colleague)
    library = await create_library(owner)
    await share(owner, library["id"], COLLEAGUE_EMAIL)
    await owner.delete(f"/api/v1/libraries/{library['id']}")

    response = await colleague.get(f"/api/v1/libraries/{library['id']}{path}")
    assert response.status_code == 404

"""Copying a library so the two can diverge.

The point of a duplicate is that changing one does not change the other.
Everything here is about that separation: the copies share stored bytes,
because those are addressed by content and immutable, and share nothing
else.
"""

from __future__ import annotations

import pytest
from control_support import UserClient
from httpx2 import AsyncClient


@pytest.fixture
def owner(client: AsyncClient) -> UserClient:
    return UserClient(client, "owner")


@pytest.fixture
def stranger(client: AsyncClient) -> UserClient:
    return UserClient(client, "stranger")


async def make_library(user: UserClient, name: str, files: int = 2) -> str:
    library = (await user.post("/api/v1/libraries", {"name": name})).json()
    for index in range(files):
        await user.upload(library["id"], f"note-{index}.txt", f"contents {index}".encode())
    return str(library["id"])


async def documents_of(user: UserClient, library_id: str) -> list[dict]:
    return (await user.get(f"/api/v1/libraries/{library_id}/documents")).json()


async def test_a_duplicate_has_the_same_documents(owner: UserClient) -> None:
    source = await make_library(owner, "Papers")

    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {})).json()

    assert copy["id"] != source
    assert copy["name"] == "Papers (copy)"
    assert sorted(d["filename"] for d in await documents_of(owner, copy["id"])) == [
        "note-0.txt",
        "note-1.txt",
    ]


async def test_the_copy_can_be_named(owner: UserClient) -> None:
    source = await make_library(owner, "Papers", files=0)

    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {"name": "My edits"})).json()

    assert copy["name"] == "My edits"


async def test_deleting_from_the_copy_leaves_the_original_alone(owner: UserClient) -> None:
    """The whole reason to duplicate rather than share."""
    source = await make_library(owner, "Papers")
    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {})).json()

    copied = await documents_of(owner, copy["id"])
    removed = await owner.delete(f"/api/v1/libraries/{copy['id']}/documents/{copied[0]['id']}")

    assert removed.status_code in (202, 204)
    assert len(await documents_of(owner, source)) == 2


async def test_adding_to_the_original_does_not_reach_the_copy(owner: UserClient) -> None:
    source = await make_library(owner, "Papers")
    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {})).json()

    await owner.upload(source, "note-2.txt", b"added later")

    assert len(await documents_of(owner, source)) == 3
    assert len(await documents_of(owner, copy["id"])) == 2


async def test_the_documents_are_different_rows(owner: UserClient) -> None:
    """Sharing document ids would make one delete remove both."""
    source = await make_library(owner, "Papers")
    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {})).json()

    original_ids = {d["id"] for d in await documents_of(owner, source)}
    copied_ids = {d["id"] for d in await documents_of(owner, copy["id"])}

    assert original_ids.isdisjoint(copied_ids)


async def test_the_copy_is_queued_for_indexing(owner: UserClient) -> None:
    """A duplicate answers questions once its documents are indexed.

    Its passages are rebuilt rather than copied from the original, so the
    copy starts where an upload starts.
    """
    source = await make_library(owner, "Papers")
    copy = (await owner.post(f"/api/v1/libraries/{source}/duplicate", {})).json()

    assert all(d["status"] == "queued" for d in await documents_of(owner, copy["id"]))


async def test_a_library_that_is_not_yours_cannot_be_duplicated(
    owner: UserClient, stranger: UserClient
) -> None:
    """404, not 403: that a library exists is itself a disclosure."""
    source = await make_library(owner, "Papers", files=0)

    response = await stranger.post(f"/api/v1/libraries/{source}/duplicate", {})

    assert response.status_code == 404
    assert (await stranger.get("/api/v1/libraries")).json() == []

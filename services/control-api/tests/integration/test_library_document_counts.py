"""What a library reports it holds.

`document_count` is not decoration. The web app prints it on the libraries
page, on every card, in the sidebar, in the command palette, and beside every
entry in the chat library picker - so a library that under-reports does not
look like a display bug, it looks like the documents have been lost.

The count therefore has to agree with what listing the library returns, and
these tests pin the two together rather than checking either alone.
"""

from __future__ import annotations

from typing import Any

from control_support import UserClient


async def create_library(user: UserClient, name: str = "Counted") -> dict[str, Any]:
    response = await user.post("/api/v1/libraries", {"name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def listed(user: UserClient, library_id: str) -> list[dict[str, Any]]:
    response = await user.get(f"/api/v1/libraries/{library_id}/documents")
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_uploaded_document_is_counted(owner: UserClient, library_id: str) -> None:
    """The regression: every library reported zero however much was in it."""
    await owner.upload(library_id, "paper.txt", b"evidence")

    response = await owner.get(f"/api/v1/libraries/{library_id}")
    assert response.status_code == 200
    assert response.json()["document_count"] == 1


async def test_the_count_matches_the_documents_that_are_listed(
    owner: UserClient, library_id: str
) -> None:
    """The property that matters, not the number in isolation.

    A count derived differently from the listing is the failure worth
    guarding: the page would show rows the header says are not there.
    """
    for index in range(3):
        uploaded = await owner.upload(library_id, f"paper{index}.txt", f"body {index}".encode())
        assert uploaded.status_code == 201, uploaded.text

    summary = (await owner.get(f"/api/v1/libraries/{library_id}")).json()
    documents = await listed(owner, library_id)

    assert len(documents) == 3, "the fixture uploaded nothing, so the count proves nothing"
    assert summary["document_count"] == len(documents)


async def test_listing_libraries_counts_each_one_separately(owner: UserClient) -> None:
    """One grouped query serves the list, so a mix is what can go wrong."""
    await create_library(owner, "Empty")
    one = await create_library(owner, "One")
    two = await create_library(owner, "Two")

    await owner.upload(one["id"], "a.txt", b"a")
    await owner.upload(two["id"], "b.txt", b"b")
    await owner.upload(two["id"], "c.txt", b"c")

    libraries = (await owner.get("/api/v1/libraries")).json()
    counts = {library["name"]: library["document_count"] for library in libraries}

    assert counts["Empty"] == 0
    assert counts["One"] == 1
    assert counts["Two"] == 2


async def test_a_deleted_document_stops_being_counted(owner: UserClient, library_id: str) -> None:
    """A tombstone is what makes a document unreachable, and uncounted with it."""
    kept = (await owner.upload(library_id, "kept.txt", b"kept")).json()
    removed = (await owner.upload(library_id, "removed.txt", b"removed")).json()

    before = (await owner.get(f"/api/v1/libraries/{library_id}")).json()
    assert before["document_count"] == 2

    response = await owner.delete(f"/api/v1/libraries/{library_id}/documents/{removed['id']}")
    assert response.status_code in {200, 202, 204}, response.text

    after = (await owner.get(f"/api/v1/libraries/{library_id}")).json()
    assert after["document_count"] == 1
    assert [document["id"] for document in await listed(owner, library_id)] == [kept["id"]]


async def test_a_new_library_holds_nothing(owner: UserClient) -> None:
    assert (await create_library(owner, "Fresh"))["document_count"] == 0

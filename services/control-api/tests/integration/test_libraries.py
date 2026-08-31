"""Private-library CRUD and cross-user isolation against real PostgreSQL."""

from __future__ import annotations

from typing import Any

from control_support import UserClient


async def create_library(user: UserClient, name: str = "Private") -> dict[str, Any]:
    response = await user.post("/api/v1/libraries", {"name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def test_owner_can_create_and_read_a_library(owner: UserClient) -> None:
    library = await create_library(owner, "Thesis sources")
    response = await owner.get(f"/api/v1/libraries/{library['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Thesis sources"
    assert response.json()["owner_user_id"] == library["owner_user_id"]


async def test_user_cannot_read_another_users_library(
    owner: UserClient, stranger: UserClient
) -> None:
    library = await create_library(owner)
    response = await stranger.get(f"/api/v1/libraries/{library['id']}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_user_cannot_rename_another_users_library(
    owner: UserClient, stranger: UserClient
) -> None:
    library = await create_library(owner)
    response = await stranger.patch(f"/api/v1/libraries/{library['id']}", {"name": "Seized"})
    assert response.status_code == 404
    unchanged = await owner.get(f"/api/v1/libraries/{library['id']}")
    assert unchanged.json()["name"] == "Private"


async def test_user_cannot_delete_another_users_library(
    owner: UserClient, stranger: UserClient
) -> None:
    library = await create_library(owner)
    assert (await stranger.delete(f"/api/v1/libraries/{library['id']}")).status_code == 404
    assert (await owner.get(f"/api/v1/libraries/{library['id']}")).status_code == 200


async def test_listing_shows_only_the_callers_libraries(
    owner: UserClient, stranger: UserClient
) -> None:
    await create_library(owner, "Mine")
    await create_library(stranger, "Theirs")
    names = [item["name"] for item in (await owner.get("/api/v1/libraries")).json()]
    assert names == ["Mine"]


async def test_a_missing_library_is_indistinguishable_from_a_forbidden_one(
    owner: UserClient, stranger: UserClient
) -> None:
    library = await create_library(owner)
    forbidden = await stranger.get(f"/api/v1/libraries/{library['id']}")
    missing = await stranger.get("/api/v1/libraries/00000000-0000-4000-8000-000000000000")
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json()["code"] == missing.json()["code"]


async def test_owner_can_rename_a_library(owner: UserClient) -> None:
    library = await create_library(owner)
    response = await owner.patch(f"/api/v1/libraries/{library['id']}", {"name": "  Renamed  "})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


async def test_rename_rejects_a_stale_update_timestamp(owner: UserClient) -> None:
    library = await create_library(owner)
    first = await owner.patch(
        f"/api/v1/libraries/{library['id']}",
        {"name": "First", "expected_updated_at": library["updated_at"]},
    )
    assert first.status_code == 200

    conflicting = await owner.patch(
        f"/api/v1/libraries/{library['id']}",
        {"name": "Second", "expected_updated_at": library["updated_at"]},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "conflict"
    assert (await owner.get(f"/api/v1/libraries/{library['id']}")).json()["name"] == "First"


async def test_deleted_libraries_disappear_from_reads_and_lists(owner: UserClient) -> None:
    library = await create_library(owner)
    assert (await owner.delete(f"/api/v1/libraries/{library['id']}")).status_code == 204
    assert (await owner.get(f"/api/v1/libraries/{library['id']}")).status_code == 404
    assert (await owner.get("/api/v1/libraries")).json() == []


async def test_deleting_twice_is_not_an_error_the_second_time(owner: UserClient) -> None:
    library = await create_library(owner)
    await owner.delete(f"/api/v1/libraries/{library['id']}")
    assert (await owner.delete(f"/api/v1/libraries/{library['id']}")).status_code == 404


async def test_library_names_are_validated(owner: UserClient) -> None:
    assert (await owner.post("/api/v1/libraries", {"name": "   "})).status_code == 422
    assert (await owner.post("/api/v1/libraries", {"name": "x" * 121})).status_code == 422


async def test_two_users_may_hold_libraries_with_the_same_name(
    owner: UserClient, stranger: UserClient
) -> None:
    assert (await create_library(owner, "Shared name"))["id"] != (
        await create_library(stranger, "Shared name")
    )["id"]


async def test_a_user_row_is_created_once_per_subject(owner: UserClient) -> None:
    await create_library(owner, "One")
    await create_library(owner, "Two")
    libraries = (await owner.get("/api/v1/libraries")).json()
    assert len({item["owner_user_id"] for item in libraries}) == 1

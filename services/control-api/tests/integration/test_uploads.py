"""Upload behavior: deduplication, format enforcement, quotas, and isolation."""

from __future__ import annotations

from pathlib import Path

from control_support import UserClient

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\ntrailer\n%%EOF\n"
DOCX_BYTES = b"PK\x03\x04\x14\x00\x06\x00word/document.xml"


def stored_objects(source_root: Path) -> list[Path]:
    sources = source_root / "sources"
    return sorted(sources.iterdir()) if sources.exists() else []


async def test_same_bytes_create_versions_referencing_one_object(
    owner: UserClient, library_id: str, source_root: Path
) -> None:
    """Deduplication is invisible at the API and total on disk."""
    first = await owner.upload(library_id, "paper.txt", b"same evidence")
    second = await owner.upload(library_id, "copy.txt", b"same evidence")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["current_version_id"] != second.json()["current_version_id"]
    assert first.json()["filename"] == "paper.txt"
    assert second.json()["filename"] == "copy.txt"
    assert len(stored_objects(source_root)) == 1


async def test_upload_is_queued_for_ingestion(owner: UserClient, library_id: str) -> None:
    summary = (await owner.upload(library_id, "notes.md", b"# Notes")).json()
    assert summary["status"] == "queued"
    assert summary["status_detail"] is None
    assert summary["media_type"] == "text/markdown"
    assert summary["byte_size"] == 7


async def test_supported_formats_are_accepted(owner: UserClient, library_id: str) -> None:
    for filename, content, media_type in [
        ("paper.pdf", PDF_BYTES, "application/pdf"),
        (
            "report.docx",
            DOCX_BYTES,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notes.md", b"# Heading", "text/markdown"),
        ("plain.txt", b"evidence", "text/plain"),
    ]:
        response = await owner.upload(library_id, filename, content)
        assert response.status_code == 201, filename
        assert response.json()["media_type"] == media_type


async def test_a_pdf_wearing_a_text_name_is_rejected(
    owner: UserClient, library_id: str, source_root: Path
) -> None:
    """The extension is never taken on trust; nor is the declared part type."""
    response = await owner.upload(library_id, "innocent.txt", PDF_BYTES)
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_content"
    assert stored_objects(source_root) == []


async def test_text_wearing_a_pdf_name_is_rejected(owner: UserClient, library_id: str) -> None:
    response = await owner.upload(library_id, "fake.pdf", b"this is not a pdf")
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_content"


async def test_unsupported_extension_is_rejected(owner: UserClient, library_id: str) -> None:
    response = await owner.upload(library_id, "tool.exe", b"MZ\x90\x00")
    assert response.status_code == 415


async def test_empty_upload_is_rejected(owner: UserClient, library_id: str) -> None:
    response = await owner.upload(library_id, "blank.txt", b"")
    assert response.status_code == 415


async def test_oversized_upload_is_rejected_and_stores_nothing(
    owner: UserClient, library_id: str, source_root: Path
) -> None:
    response = await owner.upload(library_id, "huge.txt", b"x" * 8192)
    assert response.status_code == 413
    assert response.json()["code"] == "quota_exceeded"
    assert stored_objects(source_root) == []


async def test_a_rejected_upload_leaves_no_document(owner: UserClient, library_id: str) -> None:
    """Metadata is only written once the bytes are durable."""
    await owner.upload(library_id, "fake.pdf", b"this is not a pdf")
    listed = await owner.get(f"/api/v1/libraries/{library_id}/documents")
    assert listed.json() == []


async def test_filename_is_reduced_to_a_bare_name(owner: UserClient, library_id: str) -> None:
    """A traversal attempt is stored as a plain filename, not a path."""
    summary = (await owner.upload(library_id, "../../etc/passwd.txt", b"evidence")).json()
    assert summary["filename"] == "passwd.txt"


async def test_replacement_adds_a_version_and_keeps_the_document(
    owner: UserClient, library_id: str
) -> None:
    original = (await owner.upload(library_id, "draft.txt", b"first draft")).json()
    replaced = (
        await owner.upload(library_id, "final.txt", b"second draft", document_id=original["id"])
    ).json()

    assert replaced["id"] == original["id"]
    assert replaced["current_version_id"] != original["current_version_id"]
    assert replaced["filename"] == "final.txt"

    listed = (await owner.get(f"/api/v1/libraries/{library_id}/documents")).json()
    assert len(listed) == 1


async def test_download_returns_the_stored_bytes(owner: UserClient, library_id: str) -> None:
    summary = (await owner.upload(library_id, "evidence.txt", b"exact bytes")).json()
    response = await owner.get(f"/api/v1/libraries/{library_id}/documents/{summary['id']}/content")

    assert response.status_code == 200
    assert response.content == b"exact bytes"
    assert response.headers["content-type"].startswith("text/plain")
    assert "evidence.txt" in response.headers["content-disposition"]


async def test_a_stranger_cannot_upload_to_another_library(
    stranger: UserClient, library_id: str
) -> None:
    response = await stranger.upload(library_id, "intrusion.txt", b"not yours")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_a_stranger_cannot_see_or_fetch_a_document(
    owner: UserClient, stranger: UserClient, library_id: str
) -> None:
    """Every route answers 404, so nothing distinguishes forbidden from absent."""
    summary = (await owner.upload(library_id, "private.txt", b"confidential")).json()
    base = f"/api/v1/libraries/{library_id}/documents"

    assert (await stranger.get(base)).status_code == 404
    assert (await stranger.get(f"{base}/{summary['id']}")).status_code == 404
    assert (await stranger.get(f"{base}/{summary['id']}/content")).status_code == 404
    assert (await stranger.delete(f"{base}/{summary['id']}")).status_code == 404

    still_there = await owner.get(f"{base}/{summary['id']}")
    assert still_there.status_code == 200


async def test_deleted_documents_stop_being_visible(owner: UserClient, library_id: str) -> None:
    summary = (await owner.upload(library_id, "wrong.txt", b"delete me")).json()
    base = f"/api/v1/libraries/{library_id}/documents"

    assert (await owner.delete(f"{base}/{summary['id']}")).status_code == 204
    assert (await owner.get(f"{base}/{summary['id']}")).status_code == 404
    assert (await owner.get(base)).json() == []
    assert (await owner.delete(f"{base}/{summary['id']}")).status_code == 404


async def test_deleting_a_library_hides_its_documents(owner: UserClient, library_id: str) -> None:
    """Tombstoning a library takes its documents out of reach immediately."""
    summary = (await owner.upload(library_id, "kept.txt", b"still stored")).json()
    assert (await owner.delete(f"/api/v1/libraries/{library_id}")).status_code == 204

    base = f"/api/v1/libraries/{library_id}/documents"
    assert (await owner.get(base)).status_code == 404
    assert (await owner.get(f"{base}/{summary['id']}")).status_code == 404


async def test_documents_do_not_leak_between_libraries(owner: UserClient, library_id: str) -> None:
    """A document id is only addressable under the library that holds it."""
    other = (await owner.post("/api/v1/libraries", {"name": "Other"})).json()
    summary = (await owner.upload(library_id, "here.txt", b"in the first library")).json()

    misdirected = await owner.get(f"/api/v1/libraries/{other['id']}/documents/{summary['id']}")
    assert misdirected.status_code == 404

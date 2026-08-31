"""Content-addressed storage for uploaded source bytes.

Uploads are written through `fsspec`, so a single-node deployment can point
at a local directory and a clustered one at S3 without any code change.

Bytes are never trusted. A stream is hashed and size-checked as it arrives,
its type is decided from the leading bytes rather than the client's claim,
and it only becomes reachable under its content hash once it is complete.
A failed upload leaves a temporary object behind at worst, never a
half-written source that ingestion could pick up.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

import fsspec
from anyio import to_thread

#: Enough to cover every signature below without buffering a whole file.
PREFIX_BYTES = 8192

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

#: The MVP scope: text PDF, DOCX, Markdown, and plain text. OCR is out of
#: scope, so a scanned PDF is accepted here and rejected later by the parser,
#: which is the first stage able to tell that it holds no extractable text.
SUPPORTED_EXTENSIONS = {
    ".pdf": PDF_MEDIA_TYPE,
    ".docx": DOCX_MEDIA_TYPE,
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

PDF_SIGNATURE = b"%PDF-"
#: DOCX is a ZIP container; this is the local file header every one starts with.
ZIP_SIGNATURE = b"PK\x03\x04"

BINARY_SIGNATURES = (PDF_SIGNATURE, ZIP_SIGNATURE)


class SourceStoreError(Exception):
    """A rejected upload, carrying a stable code for the HTTP layer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UnsupportedContent(SourceStoreError):
    """The bytes are not a format Primer can ingest."""


class QuotaExceeded(SourceStoreError):
    """The upload is larger than the deployment allows."""


@dataclass(frozen=True)
class StoredSource:
    """The durable result of an upload."""

    sha256: str
    byte_size: int
    media_type: str
    #: True when identical bytes were already stored. Callers still create a
    #: new version; only the underlying object is shared.
    deduplicated: bool


def _looks_like_text(prefix: bytes) -> bool:
    """Decide whether a prefix is UTF-8 text.

    A NUL byte never appears in valid UTF-8 text and is the cheapest binary
    tell. The prefix can also end mid-character simply because it is a
    prefix, so a few trailing bytes are dropped before giving up.
    """
    if b"\x00" in prefix:
        return False
    for trim in range(4):
        candidate = prefix[: len(prefix) - trim] if trim else prefix
        try:
            candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
        return True
    return False


def detect_media_type(prefix: bytes, filename: str) -> str:
    """Resolve the media type from the bytes, cross-checked against the name.

    Both must agree. Trusting the extension alone would let a caller hand the
    parser a PDF wearing a `.txt` name; trusting the content alone would let
    a library fill with files whose names promise something they are not.
    """
    extension = PurePosixPath(filename).suffix.lower()
    declared = SUPPORTED_EXTENSIONS.get(extension)
    if declared is None:
        raise UnsupportedContent(
            "unsupported_extension",
            "Primer accepts PDF, DOCX, Markdown, and plain text files.",
        )

    if declared == PDF_MEDIA_TYPE:
        if not prefix.startswith(PDF_SIGNATURE):
            raise UnsupportedContent("content_mismatch", "The file is not a PDF.")
        return declared

    if declared == DOCX_MEDIA_TYPE:
        if not prefix.startswith(ZIP_SIGNATURE):
            raise UnsupportedContent("content_mismatch", "The file is not a DOCX document.")
        return declared

    if any(prefix.startswith(signature) for signature in BINARY_SIGNATURES) or not _looks_like_text(
        prefix
    ):
        raise UnsupportedContent("content_mismatch", "The file is not UTF-8 text.")
    return declared


class SourceStore:
    """Streams uploads into an fsspec filesystem, keyed by content hash."""

    def __init__(self, url: str, *, max_bytes: int, chunk_bytes: int = 1024 * 1024) -> None:
        self._fs, self._root = fsspec.core.url_to_fs(url)
        self._max_bytes = max_bytes
        self._chunk_bytes = chunk_bytes

    @property
    def chunk_bytes(self) -> int:
        return self._chunk_bytes

    def _key(self, *parts: str) -> str:
        return str(PurePosixPath(self._root, *parts))

    async def _run(self, call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a blocking fsspec call without stalling the event loop."""
        return await to_thread.run_sync(partial(call, *args, **kwargs))

    async def _discard(self, key: str) -> None:
        try:
            await self._run(self._fs.rm_file, key)
        except Exception:  # noqa: BLE001 - a leftover temporary object is not a request failure
            return

    async def put(self, stream: AsyncIterator[bytes], *, filename: str) -> StoredSource:
        """Store a stream and return the source object it resolved to.

        The quota is enforced while reading, not afterwards, so an oversized
        upload stops costing bandwidth and disk as soon as it crosses the
        limit rather than after it has all been written.
        """
        temporary = self._key("tmp", f"{uuid4().hex}.part")
        await self._run(self._fs.makedirs, self._key("tmp"), exist_ok=True)

        digest = hashlib.sha256()
        size = 0
        prefix = b""
        try:
            handle = await self._run(self._fs.open, temporary, "wb")
            try:
                async for chunk in stream:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise QuotaExceeded(
                            "upload_too_large",
                            f"Uploads are limited to {self._max_bytes} bytes.",
                        )
                    if len(prefix) < PREFIX_BYTES:
                        prefix += chunk[: PREFIX_BYTES - len(prefix)]
                    digest.update(chunk)
                    await self._run(handle.write, chunk)
            finally:
                await self._run(handle.close)

            if size == 0:
                raise UnsupportedContent("empty_upload", "The file is empty.")
            media_type = detect_media_type(prefix, filename)

            sha256 = digest.hexdigest()
            final = self._key("sources", sha256)
            if await self._run(self._fs.exists, final):
                await self._discard(temporary)
                return StoredSource(sha256, size, media_type, deduplicated=True)

            await self._run(self._fs.makedirs, self._key("sources"), exist_ok=True)
            await self._run(self._fs.mv, temporary, final)
            return StoredSource(sha256, size, media_type, deduplicated=False)
        except BaseException:
            await self._discard(temporary)
            raise

    async def open_stream(self, sha256: str) -> AsyncIterator[bytes]:
        """Read a stored object back in bounded chunks."""
        handle = await self._run(self._fs.open, self._key("sources", sha256), "rb")
        try:
            while True:
                chunk = await self._run(handle.read, self._chunk_bytes)
                if not chunk:
                    return
                yield chunk
        finally:
            await self._run(handle.close)

    async def exists(self, sha256: str) -> bool:
        return bool(await self._run(self._fs.exists, self._key("sources", sha256)))

    async def remove(self, sha256: str) -> None:
        """Delete a stored object. Callers must confirm nothing references it."""
        await self._discard(self._key("sources", sha256))

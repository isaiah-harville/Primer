"""Format detection, which decides what reaches the parser."""

from __future__ import annotations

import pytest
from primer_storage import (
    DOCX_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    PPTX_MEDIA_TYPE,
    UnsupportedContent,
    detect_media_type,
)


@pytest.mark.parametrize(
    ("prefix", "filename", "expected"),
    [
        (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3", "paper.pdf", PDF_MEDIA_TYPE),
        (b"PK\x03\x04\x14\x00", "report.DOCX", DOCX_MEDIA_TYPE),
        (b"PK\x03\x04\x14\x00", "deck.pptx", PPTX_MEDIA_TYPE),
        (b"# Heading", "notes.md", "text/markdown"),
        (b"# Heading", "notes.markdown", "text/markdown"),
        (b"plain evidence", "quote.txt", "text/plain"),
        ("accented évidence".encode(), "quote.txt", "text/plain"),
    ],
)
def test_supported_formats_resolve(prefix: bytes, filename: str, expected: str) -> None:
    assert detect_media_type(prefix, filename) == expected


@pytest.mark.parametrize(
    ("prefix", "filename", "code"),
    [
        (b"%PDF-1.7", "disguised.txt", "content_mismatch"),
        (b"PK\x03\x04", "disguised.md", "content_mismatch"),
        (b"just text", "claimed.pptx", "content_mismatch"),
        (b"\xd0\xcf\x11\xe0", "legacy.ppt", "unsupported_extension"),
        (b"just text", "claimed.pdf", "content_mismatch"),
        (b"just text", "claimed.docx", "content_mismatch"),
        (b"\x00\x01\x02binary", "binary.txt", "content_mismatch"),
        (b"MZ\x90\x00", "tool.exe", "unsupported_extension"),
        (b"anything", "no-extension", "unsupported_extension"),
    ],
)
def test_mismatched_and_unknown_formats_are_rejected(
    prefix: bytes, filename: str, code: str
) -> None:
    with pytest.raises(UnsupportedContent) as raised:
        detect_media_type(prefix, filename)
    assert raised.value.code == code


def test_a_prefix_cut_mid_character_is_still_text() -> None:
    """The prefix is a fixed byte count, so it can split a UTF-8 sequence."""
    truncated = "long évidence".encode()[:-1]
    assert detect_media_type(truncated, "quote.txt") == "text/plain"

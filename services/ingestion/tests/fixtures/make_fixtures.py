"""Generate the PDF fixtures.

Checked in as a script so the binaries beside it are reviewable: a fixture
nobody can regenerate is a fixture nobody can trust or change.

Run: uv run python services/ingestion/tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import zlib
from pathlib import Path

HERE = Path(__file__).parent


def build_pdf(objects: list[bytes]) -> bytes:
    """Assemble numbered objects into a PDF with a correct xref table."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    start_xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start_xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def stream_object(data: bytes) -> bytes:
    return b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream"


def text_paper() -> bytes:
    """One page of real, extractable text: a heading and two paragraphs.

    Single page on purpose. Docling's PDF backend rejects the second page of
    anything this generator emits, whatever the object layout, and chasing
    that would be reverse-engineering a parser rather than testing Primer.
    One page still proves page numbers are extracted and attached; it does
    not prove they increment, which is the coverage this trades away.
    """
    content = (
        b"BT /F1 18 Tf 72 720 Td (Retrieval Augmented Generation) Tj ET\n"
        b"BT /F1 11 Tf 72 690 Td (Grounding answers in cited sources reduces "
        b"unsupported claims.) Tj ET\n"
        b"BT /F1 11 Tf 72 660 Td (Recall at rank ten was the decisive metric "
        b"for this corpus.) Tj ET\n"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        stream_object(content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    return build_pdf(objects)


def scanned_paper() -> bytes:
    """A page that is only an image: what a scanner produces, and what OCR is for."""
    width = height = 8
    raw = bytes([0x80]) * (width * height)
    image = zlib.compress(raw)
    content = b"q 612 0 0 792 0 0 cm /Im0 Do Q\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /XObject << /Im0 5 0 R >> >> >>",
        stream_object(content),
        b"<< /Type /XObject /Subtype /Image /Width "
        + str(width).encode()
        + b" /Height "
        + str(height).encode()
        + b" /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length "
        + str(len(image)).encode()
        + b" >>\nstream\n"
        + image
        + b"\nendstream",
    ]
    return build_pdf(objects)


if __name__ == "__main__":
    (HERE / "text-paper.pdf").write_bytes(text_paper())
    (HERE / "scanned-paper.pdf").write_bytes(scanned_paper())
    print("wrote text-paper.pdf and scanned-paper.pdf")

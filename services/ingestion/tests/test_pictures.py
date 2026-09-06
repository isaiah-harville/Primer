"""Text that is inside a picture rather than beside it.

Docling runs OCR only in its PDF pipeline. Everything else Primer accepts
is converted by `SimplePipeline`, which has no OCR option at any setting -
so a slide whose content is a pasted chart converted to a title and an
empty image, and the deck indexed as almost nothing while reporting ready.

The expensive test at the bottom drives the real engine. The rest use a
stand-in, because what they check is the plumbing around it and loading an
OCR model to assert a call was made is a slow way to learn nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from docling_core.types.doc import DoclingDocument
from primer_ingestion.parsing import build_converter
from primer_ingestion.pictures import MIN_READABLE_PIXELS, read_pictures

FIXTURES = Path(__file__).parent / "fixtures"
DECK_WITH_A_PICTURE = FIXTURES / "slides-with-a-picture.pptx"


def converted(path: Path) -> DoclingDocument:
    return build_converter(enable_ocr=True).convert(path, raises_on_error=False).document


def texts_of(document: DoclingDocument) -> list[str]:
    return [item.text for item in (document.texts or []) if (item.text or "").strip()]


def test_a_slide_deck_hides_its_text_inside_pictures() -> None:
    """The fault, stated as a fact about Docling rather than about Primer.

    If this ever fails because the PowerPoint pipeline learned to read
    pictures, everything below it is redundant and can go.
    """
    document = converted(DECK_WITH_A_PICTURE)

    assert texts_of(document) == ["Results"]
    assert len(document.pictures or []) == 1


def test_what_a_picture_says_reaches_the_document() -> None:
    document = converted(DECK_WITH_A_PICTURE)

    read = read_pictures(
        document, lambda _: ["Total bookings", "reached 4.2 million"], max_pictures=10
    )

    assert read == 1
    assert "Total bookings reached 4.2 million" in texts_of(document)


def test_the_text_lands_where_the_chunker_will_find_it() -> None:
    """A child of a picture is not part of the body anything walks.

    Added there it appears in `document.texts` and in nothing else - not
    the chunks, not the markdown export - so it looks stored and is not.
    The export is checked rather than the chunker because it is the same
    traversal and does not need a tokenizer.
    """
    document = converted(DECK_WITH_A_PICTURE)

    read_pictures(document, lambda _: ["Churn fell to 3.1 percent"], max_pictures=10)

    assert "Churn fell to 3.1 percent" in document.export_to_markdown()


def test_a_picture_too_small_to_hold_words_is_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bullets, logos and spacers are most of the pictures in a document,
    and each one would otherwise cost a full OCR pass to learn that."""
    from docling_core.types.doc import PictureItem
    from PIL import Image

    document = converted(DECK_WITH_A_PICTURE)
    asked: list[Any] = []
    tiny = Image.new("RGB", (MIN_READABLE_PIXELS - 1, MIN_READABLE_PIXELS - 1), "white")
    monkeypatch.setattr(PictureItem, "get_image", lambda self, doc: tiny)

    read = read_pictures(
        document, lambda image: asked.append(image) or ["something"], max_pictures=10
    )

    assert read == 0
    assert asked == []


def test_a_picture_that_cannot_be_read_does_not_fail_the_document() -> None:
    """OCR is an improvement on a document that already converted.

    Failing the upload because one embedded image was malformed would lose
    the text that did convert.
    """
    document = converted(DECK_WITH_A_PICTURE)

    def refuse(_: Any) -> list[str]:
        raise RuntimeError("that is not an image")

    assert read_pictures(document, refuse, max_pictures=10) == 0
    assert texts_of(document) == ["Results"]


def test_the_number_of_pictures_read_is_bounded() -> None:
    """A deck built entirely of screenshots is the slowest thing the worker
    does, so the ceiling stops it rather than the document."""
    document = converted(DECK_WITH_A_PICTURE)
    asked: list[Any] = []

    assert read_pictures(document, lambda i: asked.append(i) or ["x"], max_pictures=0) == 0
    assert asked == []


@pytest.mark.models
def test_a_deck_is_really_read_end_to_end() -> None:
    """The whole path with the real OCR engine, which is the thing in doubt.

    Everything above stands in for the engine, so none of it would notice
    if the engine were never reachable or produced nothing this pipeline
    could use.

    In a subprocess, and not for isolation of the assertion - for isolation
    of onnxruntime. Loading it into the interpreter that has already
    imported torch and run the fork-safety tests aborts at shutdown
    (`recursive_mutex lock failed`), after every test has passed, which
    turns a green suite into exit code 134. The engine is a native runtime
    with its own threadpool and it does not have to share a process with
    the rest of the suite to be proven.
    """
    script = f"""
import uuid
from primer_ingestion.chunking import DocumentContext
from primer_ingestion.config import Settings
from primer_ingestion.parsing import DocumentParser
from primer_storage import PPTX_MEDIA_TYPE

parser = DocumentParser(Settings(broker_url="memory://", enable_ocr=True))
chunks = parser.parse_and_chunk(
    {str(DECK_WITH_A_PICTURE)!r},
    DocumentContext(
        owner_user_id=uuid.uuid4(),
        library_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        generation_id=uuid.uuid4(),
        filename="slides-with-a-picture.pptx",
    ),
    media_type=PPTX_MEDIA_TYPE,
)
print("READ:" + " ".join(chunk.content for chunk in chunks))
"""
    finished = subprocess.run(  # noqa: S603 - a fixed interpreter on a generated script
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr[-2000:]

    written = next(
        line for line in finished.stdout.splitlines() if line.startswith("READ:")
    ).lower()
    assert "bookings" in written
    assert "4.2" in written

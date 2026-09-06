"""How a document is split, which is what a citation ends up quoting.

`HybridChunker` needs the embedding model's tokenizer. Without one, chunking
falls back to `HierarchicalChunker`, which splits on document structure and
merges nothing, so a document whose layout is many short items is stored one
line at a time. Both are real chunkers and both produce chunks, so the
fallback looks like a working install right up until someone reads a
citation and finds two words in it. These pin the two things that make the
difference visible - a warning when it happens, and a refusal when a
tokenizer was configured but is wrong.
"""

from __future__ import annotations

import logging

import pytest
from docling.chunking import HierarchicalChunker
from docling_core.transforms.chunker import BaseChunker
from primer_ingestion import chunking
from primer_ingestion.chunking import build_chunker
from primer_ingestion.config import Settings


def settings(*, chunk_tokenizer: str | None = None, max_chunk_tokens: int = 512) -> Settings:
    """The two settings these tests vary, named rather than splatted.

    `**overrides` needed a suppression to type-check, and the one it
    carried was mypy's spelling - so it silenced nothing and the checker
    reported the call site once per field on the model.
    """
    return Settings(
        broker_url="memory://",
        chunk_tokenizer=chunk_tokenizer,
        max_chunk_tokens=max_chunk_tokens,
    )


def test_structural_chunking_announces_itself(caplog: pytest.LogCaptureFixture) -> None:
    """Silent, this is a bug whose symptom points nowhere near its cause.

    Someone reading "citations quote one word" has no reason to look at an
    unset environment variable, so the worker has to say so itself.
    """
    with caplog.at_level(logging.WARNING):
        chunker = build_chunker(settings())

    assert isinstance(chunker, HierarchicalChunker)
    # The variable is named, because the message is the whole fix.
    assert "PRIMER_CHUNK_TOKENIZER" in caplog.text


def test_a_configured_tokenizer_is_not_quietly_abandoned(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Falling back here would answer a misconfiguration by doing the exact
    thing the setting exists to prevent, and would do it silently.

    This raises during worker startup, so the deployment crash-loops with a
    legible reason rather than failing documents one at a time.
    """

    def refuse(*_: object, **__: object) -> object:
        raise OSError("not a known repository")

    monkeypatch.setattr(chunking.HuggingFaceTokenizer, "from_pretrained", refuse)

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError) as raised:
        build_chunker(settings(chunk_tokenizer="nobody/not-a-real-model"))

    assert "nobody/not-a-real-model" in str(raised.value)
    assert "PRIMER_CHUNK_TOKENIZER" not in caplog.text


def test_a_tokenizer_bounds_chunks_by_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured ceiling has to reach the tokenizer, not just be read.

    Loading a real tokenizer would download one, so what is checked is the
    argument: `max_tokens` is what the chunker measures against, and a
    default silently used in place of the configured value would size every
    chunk in the deployment wrongly.
    """
    tokenizer_args: dict[str, object] = {}
    chunker_args: dict[str, object] = {}

    def record_tokenizer(name: str, **kwargs: object) -> object:
        tokenizer_args["name"] = name
        tokenizer_args.update(kwargs)
        return object()

    def record_chunker(**kwargs: object) -> BaseChunker:
        chunker_args.update(kwargs)
        # A real chunker, because `build_chunker` promises to return one and
        # a test that let it return a dict would be checking a shape the
        # caller can never receive.
        return HierarchicalChunker()

    monkeypatch.setattr(chunking.HuggingFaceTokenizer, "from_pretrained", record_tokenizer)
    monkeypatch.setattr(chunking, "HybridChunker", record_chunker)

    build_chunker(settings(chunk_tokenizer="BAAI/bge-m3", max_chunk_tokens=1024))

    assert tokenizer_args == {"name": "BAAI/bge-m3", "max_tokens": 1024}
    # Peers merged, which is the half of the fix that makes small pieces
    # into passages rather than only capping large ones.
    assert chunker_args["merge_peers"] is True

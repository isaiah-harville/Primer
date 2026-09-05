"""Thinking an endpoint separated for us must survive reaching Primer.

There are two ways a reasoning model's thinking arrives, and Primer has to
handle both. One is `<think>` tags inside the content, which
`ReasoningSplitter` pulls apart. The other is a field of its own beside the
content, which is what a server does once its reasoning parser is turned on
- vLLM's `--reasoning-parser`, llama.cpp's `--reasoning-format`, DeepSeek's
API.

The second was silently broken. Haystack builds a `StreamingChunk`'s `meta`
from a fixed set of keys and `reasoning_content` is not among them, so the
field was dropped between the wire and the callback. The effect was
backwards from what anyone would guess: configuring a server to separate
reasoning *properly* moved the thinking out of the content, where Primer
could see it, and into the field that was being thrown away.

These drive the real Haystack conversion rather than a stand-in, because a
stand-in would have agreed with Primer about a key Haystack never sets.
"""

from __future__ import annotations

from typing import Any

import pytest
from haystack.components.generators.chat.openai import (
    _convert_chat_completion_chunk_to_streaming_chunk,
)
from openai.types.chat import ChatCompletionChunk
from primer_chat.generation import (
    CARRIED_REASONING,
    ReasoningCarried,
    _delta_reasoning,
    _reasoning_of,
)


def wire_chunk(**delta: Any) -> ChatCompletionChunk:
    """A streaming chunk exactly as an OpenAI-compatible server sends one."""
    return ChatCompletionChunk.model_validate(
        {
            "id": "chunk-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "a-reasoning-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
    )


def converted(chunk: ChatCompletionChunk) -> Any:
    return _convert_chat_completion_chunk_to_streaming_chunk(
        chunk=chunk, previous_chunks=[], component_info=None
    )


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_the_field_survives_the_client_but_not_the_conversion(field: str) -> None:
    """The bug, stated as a fact about the library rather than about Primer.

    If this ever fails because Haystack started carrying the field itself,
    the rescue below is redundant and can go.
    """
    chunk = wire_chunk(role="assistant", content="", **{field: "Working it out."})

    assert _delta_reasoning(chunk) == "Working it out."
    assert CARRIED_REASONING not in converted(chunk).meta


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_a_carried_thought_is_found_again(field: str) -> None:
    """What the rescue puts back, `_reasoning_of` picks up."""
    chunk = converted(wire_chunk(role="assistant", content="", **{field: "Working it out."}))
    chunk.meta[CARRIED_REASONING] = _delta_reasoning(
        wire_chunk(role="assistant", content="", **{field: "Working it out."})
    )

    assert _reasoning_of(chunk) == "Working it out."


def test_an_ordinary_chunk_carries_no_thinking() -> None:
    """Most models do not reason aloud, and must be left alone."""
    chunk = wire_chunk(role="assistant", content="The answer.")

    assert _delta_reasoning(chunk) == ""
    assert _reasoning_of(converted(chunk)) == ""


def test_the_generator_rescues_thinking_across_a_whole_stream() -> None:
    """End to end through Haystack's own loop, which is the thing in doubt.

    `_handle_stream_response` is what Haystack calls with the raw stream, so
    driving it directly exercises the interleaving the rescue depends on:
    one raw chunk pulled, converted, and handed to the callback, in that
    order, before the next is read.
    """
    stream = [
        wire_chunk(role="assistant", content=""),
        wire_chunk(content="", reasoning_content="First I check the figure. "),
        wire_chunk(content="", reasoning_content="Then I answer."),
        wire_chunk(content="It doubled."),
    ]
    generator = ReasoningCarried.__new__(ReasoningCarried)
    seen: list[Any] = []

    ReasoningCarried._handle_stream_response(generator, iter(stream), seen.append)

    assert [_reasoning_of(chunk) for chunk in seen] == [
        "",
        "First I check the figure. ",
        "Then I answer.",
        "",
    ]
    # The answer is untouched: thinking is a separate channel, and folding
    # it into the content is the failure this whole path exists to avoid.
    assert "".join(chunk.content for chunk in seen) == "It doubled."

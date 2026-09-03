"""Telling a model's thinking apart from its answer.

Reasoning models say two different things at once, and a deployment gets
them in one of two shapes depending on how the endpoint is configured.

An endpoint running a reasoning parser - vLLM with `--reasoning-parser`, or
a hosted API that does the same - sends thinking in a field of its own,
beside the content. Nothing needs separating there; it arrives separated.

An endpoint without one sends everything in the content, with the thinking
wrapped in `<think>` tags. That is the common case for a self-hosted Qwen or
DeepSeek distillation, and it is what this module is for: the tags arrive
split across streamed fragments as readily as anywhere else, so `</thi` can
be the whole of one chunk, and a naive `str.replace` shows the reader half a
tag before deciding it was one.

Every `<think>` enters thinking and every `</think>` leaves it, wherever
they appear. Models do re-enter thinking part way through an answer, and the
alternative rule - only honouring a tag at the very start - lets that raw
markup through into the prose, which is the loud, visible failure. The cost
is that a model asked to write about the tags themselves has some of that
answer filed as thinking, which is both rarer and quieter.

What this deliberately does not do is guess. Some servers emit only the
closing tag, having put the opening one in the prompt template, which makes
the leading text reasoning that only reveals itself paragraphs later. Doing
that while streaming means holding the whole answer back on the chance a
`</think>` is coming, so an ordinary answer would arrive all at once at the
end. Text that does not open with a tag is treated as an answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

OPEN = "<think>"
CLOSE = "</think>"

#: How much has to be held back to recognize a tag arriving in pieces. One
#: short of the longest tag: any more and a complete tag is being withheld,
#: any less and the end of one could be emitted as text.
HOLD = max(len(OPEN), len(CLOSE)) - 1


class Channel(StrEnum):
    """Which of the two things a model is saying."""

    ANSWER = "answer"
    REASONING = "reasoning"


@dataclass(frozen=True)
class Fragment:
    """A piece of a stream, and which channel it belongs to."""

    channel: Channel
    text: str


class ReasoningSplitter:
    """Sorts a stream of text fragments into thinking and answer.

    Stateful by necessity: whether a fragment is thinking depends on a tag
    that may have arrived several fragments ago, and whether its last few
    characters may be emitted depends on a tag that has not finished
    arriving. Feed fragments in order and call `finish` at the end, which
    releases anything held back for a tag that never completed.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_reasoning = False

    def feed(self, text: str) -> Iterator[Fragment]:
        """Sort one fragment, holding back anything that may yet be a tag."""
        self._buffer += text
        yield from self._drain(final=False)

    def finish(self) -> Iterator[Fragment]:
        """Release whatever is left, tag or not.

        A stream that ends mid-tag ends mid-tag; the characters are the
        model's output and are shown rather than swallowed.
        """
        yield from self._drain(final=True)

    def _drain(self, *, final: bool) -> Iterator[Fragment]:
        while self._buffer:
            marker = CLOSE if self._in_reasoning else OPEN
            index = self._buffer.find(marker)

            if index != -1:
                before = self._buffer[:index]
                self._buffer = self._buffer[index + len(marker) :]
                if before:
                    yield from self._emit(before)
                self._in_reasoning = marker is OPEN
                continue

            # No complete marker. Everything but a possible partial one at
            # the end can be emitted; the tail waits for the next fragment.
            keep = 0 if final else self._partial_tail(marker)
            ready, self._buffer = (
                self._buffer[: len(self._buffer) - keep],
                self._buffer[len(self._buffer) - keep :],
            )
            if ready:
                yield from self._emit(ready)
            return

    def _partial_tail(self, marker: str) -> int:
        """How many trailing characters could be the start of `marker`."""
        for length in range(min(HOLD, len(self._buffer)), 0, -1):
            if marker.startswith(self._buffer[-length:]):
                return length
        return 0

    def _emit(self, text: str) -> Iterator[Fragment]:
        if not text:
            return
        yield Fragment(Channel.REASONING if self._in_reasoning else Channel.ANSWER, text)

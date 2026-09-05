"""Telling a model's thinking apart from its answer.

Reasoning models say two different things at once, and a deployment gets
them in one of two shapes depending on how the endpoint is configured.

An endpoint running a reasoning parser - vLLM with `--reasoning-parser`,
llama.cpp with `--reasoning-format`, or a hosted API that does the same -
sends thinking in a field of its own, beside the content. Nothing needs
separating there; it arrives separated.

An endpoint without one sends everything in the content, with the thinking
wrapped in tags. That is the common case for a self-hosted model, and it is
what this module is for: the tags arrive split across streamed fragments as
readily as anywhere else, so `</thi` can be the whole of one chunk, and a
naive `str.replace` shows the reader half a tag before deciding it was one.

Which tags depends on who trained the model, and the difference is not
cosmetic. A splitter that knows only `<think>` finds nothing to separate in
a Mistral answer, and hands the reader either raw markup in the middle of
the prose or a page of scratch work where the reply should be. `DELIMITERS`
is the set Primer recognizes.

An opening tag enters thinking and its own closing tag leaves it, wherever
they appear. Pairs are never crossed: once `<think>` has opened, only
`</think>` closes it, and another family's tags inside that thought are text
like any other. Models do re-enter thinking part way through an answer, and
the alternative rule - only honouring a tag at the very start - lets that
raw markup through into the prose, which is the loud, visible failure. The
cost is that a model asked to write about the tags themselves has some of
that answer filed as thinking, which is both rarer and quieter.

What this deliberately does not do is guess. Some servers emit only the
closing tag, having put the opening one in the prompt template, which makes
the leading text reasoning that only reveals itself paragraphs later. Doing
that while streaming means holding the whole answer back on the chance a
closing tag is coming, so an ordinary answer would arrive all at once at the
end. Text that does not open with a tag is treated as an answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Delimiters:
    """One family's way of marking where its thinking starts and stops."""

    open: str
    close: str


#: The tag pairs Primer separates.
#:
#: Taken from what inference servers actually parse rather than from what a
#: model card describes: llama.cpp carries a handler per model family, and
#: these are the plain tag pairs among them. A family absent from here is
#: not unsupported - an endpoint configured to separate thinking itself
#: sends it in its own field, and never reaches this module.
#:
#: The channel protocols are deliberately absent. GPT-OSS opens thinking
#: with `<|channel|>analysis<|message|>` and ends it with `<|end|>`, which
#: also ends things that are not thinking; read as a closing tag it would
#: cut an answer in half. Those need the protocol parsed, not a pair matched.
#:
#: No tag here may be a prefix of another. That is what lets the earliest
#: match win without checking whether a longer tag starts in the same place,
#: and a test holds it so that adding a pair cannot quietly break it.
DELIMITERS: tuple[Delimiters, ...] = (
    #: DeepSeek-R1, Qwen3, QwQ, GLM, and most open reasoning models.
    Delimiters("<think>", "</think>"),
    #: Mistral: Magistral, and the Ministral 3 reasoning models.
    Delimiters("[THINK]", "[/THINK]"),
    #: MiniMax.
    Delimiters("<mm:think>", "</mm:think>"),
)


class Channel(StrEnum):
    """Which of the two things a model is saying."""

    ANSWER = "answer"
    REASONING = "reasoning"


@dataclass(frozen=True)
class Fragment:
    """A piece of a stream, and which channel it belongs to."""

    channel: Channel
    text: str


def _opened_by(tag: str) -> Delimiters:
    """The pair an opening tag belongs to, so its own closer ends it."""
    return next(pair for pair in DELIMITERS if pair.open == tag)


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
        #: The pair currently open, or None while an answer is running.
        self._open: Delimiters | None = None

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

    def _expected(self) -> tuple[str, ...]:
        """The tags that mean anything where the stream currently is.

        Inside a thought that is one tag, the one that ends it. This is what
        keeps the pairs from crossing, and it also keeps the wait short:
        only a tag that could actually come next has to be held back for.
        """
        if self._open is not None:
            return (self._open.close,)
        return tuple(pair.open for pair in DELIMITERS)

    def _drain(self, *, final: bool) -> Iterator[Fragment]:
        while self._buffer:
            expected = self._expected()
            found = self._find(expected)

            if found is None:
                # Everything but a possible partial tag at the end can be
                # emitted; the tail waits for the next fragment.
                keep = 0 if final else self._partial_tail(expected)
                cut = len(self._buffer) - keep
                ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
                if ready:
                    yield from self._emit(ready)
                return

            index, tag = found
            before = self._buffer[:index]
            self._buffer = self._buffer[index + len(tag) :]
            # Before the channel changes: what came before the tag belongs
            # to the side of it the stream was already on.
            if before:
                yield from self._emit(before)
            self._open = None if self._open else _opened_by(tag)

    def _find(self, tags: tuple[str, ...]) -> tuple[int, str] | None:
        """The earliest of `tags` in the buffer, and which one it is.

        No two can match in the same place, because no tag is a prefix of
        another - so the earliest is unambiguous.
        """
        present = [(self._buffer.find(tag), tag) for tag in tags]
        found = [entry for entry in present if entry[0] != -1]
        return min(found) if found else None

    def _partial_tail(self, tags: tuple[str, ...]) -> int:
        """How many trailing characters could be the start of one of `tags`."""
        longest = max(len(tag) for tag in tags) - 1
        for length in range(min(longest, len(self._buffer)), 0, -1):
            tail = self._buffer[-length:]
            if any(tag.startswith(tail) for tag in tags):
                return length
        return 0

    def _emit(self, text: str) -> Iterator[Fragment]:
        if not text:
            return
        yield Fragment(Channel.REASONING if self._open else Channel.ANSWER, text)

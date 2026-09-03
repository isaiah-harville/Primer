"""The model boundary.

Chat talks to any OpenAI-compatible endpoint - vLLM, Ollama, llama.cpp, or a
hosted API. The generator is a protocol so the orchestration can be tested
without one, and so swapping Haystack's client later touches one class.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Protocol

import anyio
import anyio.from_thread
import anyio.to_thread
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from primer_contracts.chat import MessageRole

from primer_chat.config import Settings
from primer_chat.rag import HistoryTurn
from primer_chat.reasoning import Channel, Fragment, ReasoningSplitter

#: Where an endpoint that separates thinking itself puts it. There is no
#: standard for this - it is not in the OpenAI API - so the field is whatever
#: a given server chose. These are the two in circulation: `reasoning_content`
#: from vLLM's reasoning parsers and DeepSeek, `reasoning` from others.
REASONING_FIELDS = ("reasoning_content", "reasoning")


def _reasoning_of(chunk: object) -> str:
    """Thinking a provider handed over already separated, if it did.

    Haystack keeps fields it does not model itself in `meta`, so both are
    looked at: the attribute for a client that grew one, and the bag for
    everything else.
    """
    meta = getattr(chunk, "meta", None) or {}
    for field in REASONING_FIELDS:
        value = getattr(chunk, field, None) or (meta.get(field) if isinstance(meta, dict) else None)
        if isinstance(value, str) and value:
            return value
    return ""


class ChatGenerator(Protocol):
    """Yields fragments as the model produces them, thinking and answer apart."""

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        history: tuple[HistoryTurn, ...] = (),
        model: str | None = None,
    ) -> AsyncIterator[Fragment]: ...


class HaystackChatGenerator:
    """Streams from an OpenAI-compatible endpoint through Haystack.

    One client per model, made on first use and kept. They are cheap to hold
    and not free to build, and a deployment offering several models will use
    each of them repeatedly.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._generators: dict[str, OpenAIChatGenerator] = {}

    @property
    def model(self) -> str:
        return self._settings.chat_model

    def _for(self, model: str | None) -> OpenAIChatGenerator:
        """A client for one model.

        The name is not validated here. Whether a user may ask for a model is
        a question about the request, answered where the request is handled;
        by this point it has been.
        """
        name = model or self._settings.chat_model
        if name not in self._generators:
            key = self._settings.chat_api_key
            self._generators[name] = OpenAIChatGenerator(
                api_key=Secret.from_token(key.get_secret_value() if key else "none"),
                model=name,
                api_base_url=self._settings.chat_base_url,
                timeout=self._settings.chat_timeout_seconds,
            )
        return self._generators[name]

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        history: tuple[HistoryTurn, ...] = (),
        model: str | None = None,
    ) -> AsyncIterator[Fragment]:
        """Bridge Haystack's synchronous callback into an async iterator.

        Haystack streams by invoking a callback on a worker thread. The
        fragments are handed across a memory channel so the event loop keeps
        serving other connections while a slow model produces tokens.

        Thinking and answer come out on separate channels. An endpoint
        running a reasoning parser hands them over already separated, in a
        field beside the content; one without a parser puts the thinking in
        the content inside `<think>` tags, which the splitter pulls back
        apart. Both are handled, because which of the two a deployment gets
        is a property of how its endpoint was launched, not of Primer.
        """
        send, receive = anyio.create_memory_object_stream[Fragment | None](max_buffer_size=64)
        splitter = ReasoningSplitter()

        def on_chunk(chunk: object) -> None:
            # A provider that separates thinking itself needs no parsing, and
            # must not be fed through the splitter: its content field carries
            # no tags, and its reasoning is not the answer.
            thought = _reasoning_of(chunk)
            if thought:
                anyio.from_thread.run(send.send, Fragment(Channel.REASONING, thought))
            text = getattr(chunk, "content", "") or ""
            for fragment in splitter.feed(text):
                anyio.from_thread.run(send.send, fragment)

        async def produce() -> None:
            try:
                await anyio.to_thread.run_sync(
                    lambda: self._run(system_prompt, user_prompt, history, on_chunk, model)
                )
            finally:
                # Anything the splitter was holding back for a tag that never
                # arrived belongs to the reader, not to the parser.
                for fragment in splitter.finish():
                    await send.send(fragment)
                await send.send(None)

        async with anyio.create_task_group() as group:
            group.start_soon(produce)
            async with receive:
                async for item in receive:
                    if item is None:
                        break
                    yield item

    def _run(
        self,
        system_prompt: str,
        user_prompt: str,
        history: tuple[HistoryTurn, ...],
        on_chunk: object,
        model: str | None,
    ) -> None:
        self._for(model).run(
            messages=[
                ChatMessage.from_system(system_prompt),
                *_replay(history),
                ChatMessage.from_user(user_prompt),
            ],
            streaming_callback=on_chunk,  # ty: ignore[invalid-argument-type]
        )


def _replay(history: tuple[HistoryTurn, ...]) -> list[ChatMessage]:
    """Earlier turns, as messages between the system prompt and the question.

    The system prompt is not replayed with them. It describes how to answer
    the question being asked now - which passages are in front of the model,
    and how they may be numbered - and an older copy of those instructions
    would be describing passages that are no longer there.
    """
    return [
        ChatMessage.from_user(turn.content)
        if turn.role is MessageRole.USER
        else ChatMessage.from_assistant(turn.content)
        for turn in history
    ]


class StaticGenerator:
    """A generator that replays fixed fragments. For tests and for offline use.

    Plain strings are answer text, which is what almost every caller wants.
    A caller exercising a reasoning model passes `Fragment`s instead and says
    which channel each belongs to.
    """

    def __init__(
        self, fragments: Iterator[str | Fragment] | list[str | Fragment], model: str = "static"
    ) -> None:
        self._fragments = [
            fragment if isinstance(fragment, Fragment) else Fragment(Channel.ANSWER, fragment)
            for fragment in fragments
        ]
        self.model = model

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        history: tuple[HistoryTurn, ...] = (),
        model: str | None = None,
    ) -> AsyncIterator[Fragment]:
        for fragment in self._fragments:
            yield fragment

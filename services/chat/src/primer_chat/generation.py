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

from primer_chat.config import Settings


class ChatGenerator(Protocol):
    """Yields text fragments as the model produces them."""

    def stream(
        self, system_prompt: str, user_prompt: str, *, model: str | None = None
    ) -> AsyncIterator[str]: ...


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
        self, system_prompt: str, user_prompt: str, *, model: str | None = None
    ) -> AsyncIterator[str]:
        """Bridge Haystack's synchronous callback into an async iterator.

        Haystack streams by invoking a callback on a worker thread. The
        fragments are handed across a memory channel so the event loop keeps
        serving other connections while a slow model produces tokens.
        """
        send, receive = anyio.create_memory_object_stream[str | None](max_buffer_size=64)

        def on_chunk(chunk: object) -> None:
            text = getattr(chunk, "content", "") or ""
            if text:
                anyio.from_thread.run(send.send, text)

        async def produce() -> None:
            try:
                await anyio.to_thread.run_sync(
                    lambda: self._run(system_prompt, user_prompt, on_chunk, model)
                )
            finally:
                await send.send(None)

        async with anyio.create_task_group() as group:
            group.start_soon(produce)
            async with receive:
                async for item in receive:
                    if item is None:
                        break
                    yield item

    def _run(
        self, system_prompt: str, user_prompt: str, on_chunk: object, model: str | None
    ) -> None:
        self._for(model).run(
            messages=[
                ChatMessage.from_system(system_prompt),
                ChatMessage.from_user(user_prompt),
            ],
            streaming_callback=on_chunk,  # ty: ignore[invalid-argument-type]
        )


class StaticGenerator:
    """A generator that replays fixed fragments. For tests and for offline use."""

    def __init__(self, fragments: Iterator[str] | list[str], model: str = "static") -> None:
        self._fragments = list(fragments)
        self.model = model

    async def stream(
        self, system_prompt: str, user_prompt: str, *, model: str | None = None
    ) -> AsyncIterator[str]:
        for fragment in self._fragments:
            yield fragment

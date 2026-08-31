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

    def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]: ...


class HaystackChatGenerator:
    """Streams from an OpenAI-compatible endpoint through Haystack."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        key = settings.chat_api_key
        self._generator = OpenAIChatGenerator(
            api_key=Secret.from_token(key.get_secret_value() if key else "none"),
            model=settings.chat_model,
            api_base_url=settings.chat_base_url,
            timeout=settings.chat_timeout_seconds,
        )

    @property
    def model(self) -> str:
        return self._settings.chat_model

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
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
                    lambda: self._run(system_prompt, user_prompt, on_chunk)
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

    def _run(self, system_prompt: str, user_prompt: str, on_chunk: object) -> None:
        self._generator.run(
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

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        for fragment in self._fragments:
            yield fragment

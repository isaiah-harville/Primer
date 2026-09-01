"""Test helpers and fakes for the Chat integration suite.

Named for its suite rather than `support`, and holding the fakes rather than
leaving them in conftest: every test directory goes on sys.path, so a shared
name shadows, and `conftest` in particular resolves to whichever one is
found first.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from httpx2 import AsyncClient, Response
from primer_chat.clients import LibraryForbidden
from primer_contracts.identity import Principal
from primer_contracts.indexing import LibraryScope, SearchRequest, SearchResult
from primer_contracts.retrieval import RetrievedChunk, SourceLocator

LIBRARY_ID = uuid.uuid5(uuid.NAMESPACE_URL, "chat-library")
OTHER_LIBRARY_ID = uuid.uuid5(uuid.NAMESPACE_URL, "other-library")
GENERATION_ID = uuid.uuid5(uuid.NAMESPACE_URL, "chat-generation")


class FakeControl:
    """Control, recording every authorization question it was asked."""

    def __init__(self, *, allowed: set[UUID] | None = None) -> None:
        self.allowed = allowed if allowed is not None else {LIBRARY_ID}
        self.asked: list[tuple[str, UUID]] = []
        self.generations: tuple[UUID, ...] = (GENERATION_ID,)

    async def library_scope(self, principal: Principal, library_id: UUID) -> LibraryScope:
        self.asked.append((principal.subject, library_id))
        if library_id not in self.allowed:
            raise LibraryForbidden(str(library_id))
        return LibraryScope(library_id=library_id, generation_ids=self.generations)


class FakeRetrieval:
    """Retrieval, recording every search so the tests can prove one never happened."""

    def __init__(self, contents: list[str] | None = None) -> None:
        self.contents = contents if contents is not None else ["The conclusion is well supported."]
        self.searches: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> SearchResult:
        self.searches.append(request)
        return SearchResult(
            chunks=tuple(
                RetrievedChunk(
                    chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, f"chunk-{index}-{content}"),
                    library_id=request.library_id,
                    document_id=uuid.uuid5(uuid.NAMESPACE_URL, "document"),
                    document_version_id=uuid.uuid5(uuid.NAMESPACE_URL, "version"),
                    content=content,
                    score=1.0 - index / 100,
                    locator=SourceLocator(page=index + 1, section="Findings"),
                    index_generation=request.generation_ids[0],
                )
                for index, content in enumerate(self.contents)
            )
        )


class FakeGenerator:
    """A model, recording the prompts it was given."""

    model = "fake-model"

    def __init__(self, fragments: list[str] | None = None, fail: bool = False) -> None:
        self.fragments = fragments if fragments is not None else ["Grounded ", "answer [1]."]
        self.fail = fail
        self.prompts: list[tuple[str, str]] = []

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        self.prompts.append((system_prompt, user_prompt))
        for index, fragment in enumerate(self.fragments):
            if self.fail and index == 1:
                raise RuntimeError("the endpoint went away")
            yield fragment


def parse_events(body: str) -> list[dict[str, Any]]:
    """Read an SSE body back into the events it framed."""
    events = []
    for block in body.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        payload = next(
            (line[len("data: ") :] for line in block.splitlines() if line.startswith("data: ")),
            None,
        )
        if payload is not None:
            events.append(json.loads(payload))
    return events


class ChatUser:
    """One edge-authenticated subject talking to Chat."""

    def __init__(self, http: AsyncClient, subject: str) -> None:
        self._http = http
        self._headers = {"X-Auth-Request-User": subject}

    async def ask(self, library_id: str, message: str) -> list[dict[str, Any]]:
        response = await self._http.post(
            "/api/v1/conversations",
            json={"library_id": library_id, "message": message},
            headers=self._headers,
        )
        return parse_events(response.text)

    async def follow_up(self, conversation_id: str, message: str) -> Response:
        return await self._http.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message},
            headers=self._headers,
        )

    async def post(self, path: str, payload: dict[str, Any] | None = None) -> Response:
        return await self._http.post(path, json=payload or {}, headers=self._headers)

    async def get(self, path: str) -> Response:
        return await self._http.get(path, headers=self._headers)

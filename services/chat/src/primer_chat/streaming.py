"""Turning a question into a stream of events.

The order of operations is the security property. Authorization happens
first and the answer is never begun without it, so an unauthorized question
reaches neither Retrieval nor a model. Citations are emitted before any text,
because they are known before any text exists - they come from what was
retrieved, not from what is written.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from primer_contracts.chat import (
    CitationEvent,
    MessageCompleted,
    MessageDelta,
    MessageRole,
    MessageStarted,
    MessageState,
    StreamError,
)
from primer_contracts.identity import Principal
from primer_contracts.indexing import SearchRequest
from sqlalchemy.ext.asyncio import AsyncSession

from primer_chat.clients import LibraryAuthority, LibraryForbidden, PassageSource
from primer_chat.config import Settings
from primer_chat.generation import ChatGenerator
from primer_chat.models import Conversation
from primer_chat.rag import NO_CONTEXT_REPLY, SYSTEM_PROMPT, build_context, build_prompt
from primer_chat.repository import ChatRepository, summarize_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answering:
    """Everything one turn needs, resolved before any of it begins."""

    principal: Principal
    conversation: Conversation
    question: str


class Responder:
    """Runs one turn and yields the events it produces."""

    def __init__(
        self,
        settings: Settings,
        control: LibraryAuthority,
        retrieval: PassageSource,
        generator: ChatGenerator,
    ) -> None:
        self._settings = settings
        self._control = control
        self._retrieval = retrieval
        self._generator = generator

    async def respond(
        self, session: AsyncSession, turn: Answering
    ) -> AsyncIterator[
        MessageStarted | MessageDelta | CitationEvent | MessageCompleted | StreamError
    ]:
        """Answer one question, emitting events as the answer takes shape."""
        repository = ChatRepository(session)
        conversation = turn.conversation
        event_id = 0

        def next_id() -> int:
            nonlocal event_id
            current = event_id
            event_id += 1
            return current

        await repository.add_message(
            conversation,
            role=MessageRole.USER,
            state=MessageState.COMPLETED,
            content=turn.question,
        )
        message = await repository.add_message(
            conversation,
            role=MessageRole.ASSISTANT,
            state=MessageState.STREAMING,
            provider_model=getattr(self._generator, "model", None),
        )
        await session.commit()

        yield MessageStarted(id=next_id(), message_id=message.id, conversation_id=conversation.id)

        # Authorization before retrieval, and retrieval before generation:
        # a question the principal may not ask reaches neither.
        try:
            scope = await self._control.library_scope(turn.principal, conversation.library_id)
        except LibraryForbidden:
            await repository.finish_message(
                message, state=MessageState.FAILED, content="", error_code="library_unavailable"
            )
            await session.commit()
            yield StreamError(
                id=next_id(),
                code="library_unavailable",
                detail="That library is no longer available to you.",
            )
            return

        chunks = ()
        if scope.generation_ids:
            result = await self._retrieval.search(
                SearchRequest(
                    principal=turn.principal,
                    library_id=conversation.library_id,
                    generation_ids=scope.generation_ids,
                    query=turn.question,
                    limit=self._settings.retrieval_limit,
                )
            )
            chunks = result.chunks

        context = build_context(chunks)
        for index, citation in enumerate(context.citations, start=1):
            yield CitationEvent(id=next_id(), index=index, citation=citation)

        if context.is_empty:
            # Nothing to ground an answer in. Saying so is the answer; asking
            # a model anyway would produce exactly the unsourced prose Primer
            # exists to avoid.
            completed = await repository.finish_message(
                message, state=MessageState.COMPLETED, content=NO_CONTEXT_REPLY
            )
            await session.commit()
            yield MessageDelta(id=next_id(), text=NO_CONTEXT_REPLY)
            yield MessageCompleted(id=next_id(), message=summarize_message(completed))
            return

        text = ""
        try:
            async for fragment in self._generator.stream(
                SYSTEM_PROMPT, build_prompt(turn.question, context)
            ):
                text += fragment
                yield MessageDelta(id=next_id(), text=fragment)
        except Exception:
            # Whatever was written is kept: it is the only evidence of what
            # went wrong, and a reader can see the answer stops mid-thought.
            logger.exception("message %s: generation failed", message.id)
            await repository.finish_message(
                message,
                state=MessageState.FAILED,
                content=text,
                citations=context.citations,
                error_code="generation_failed",
            )
            await session.commit()
            yield StreamError(
                id=next_id(),
                code="generation_failed",
                detail="The model stopped before finishing this answer.",
            )
            return

        completed = await repository.finish_message(
            message,
            state=MessageState.COMPLETED,
            content=text,
            citations=context.citations,
        )
        await session.commit()
        yield MessageCompleted(
            id=next_id(), message=summarize_message(completed, context.citations)
        )

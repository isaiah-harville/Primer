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

from primer_chat.budget import estimate_tokens, history_that_fits, passages_that_fit
from primer_chat.clients import LibraryAuthority, LibraryForbidden, PassageSource
from primer_chat.config import Settings
from primer_chat.generation import ChatGenerator
from primer_chat.models import Conversation
from primer_chat.rag import (
    NO_CONTEXT_REPLY,
    SYSTEM_PROMPT,
    UNGROUNDED_SYSTEM_PROMPT,
    build_context,
    build_prompt,
)
from primer_chat.repository import ChatRepository, summarize_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answering:
    """Everything one turn needs, resolved before any of it begins."""

    principal: Principal
    conversation: Conversation
    question: str
    #: Already checked against what this deployment offers. None means its
    #: default, which is the same thing a request with no preference gets.
    model: str | None = None


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

    @property
    def _characters_per_token(self) -> float:
        return self._settings.chat_characters_per_token

    def _window(self, turn: Answering) -> int:
        """The model's context, less the room the answer itself needs."""
        return self._settings.context_tokens(turn.model) - self._settings.chat_reply_tokens

    def _room_for_passages(self, turn: Answering, system_prompt: str) -> int:
        """What the passages may cost, before any history is considered.

        Measured against a prompt with no passages in it, so the question and
        the scaffolding around it are paid for first. History is fitted
        afterwards into whatever the passages leave.
        """
        empty = build_prompt(turn.question, build_context(()))
        return (
            self._window(turn)
            - estimate_tokens(system_prompt, characters_per_token=self._characters_per_token)
            - estimate_tokens(empty, characters_per_token=self._characters_per_token)
        )

    async def respond(
        self, session: AsyncSession, turn: Answering
    ) -> AsyncIterator[
        MessageStarted | MessageDelta | CitationEvent | MessageCompleted | StreamError
    ]:
        """Answer one question, emitting events as the answer takes shape."""
        repository = ChatRepository(session)
        conversation = turn.conversation
        event_id = 0

        # Read before this turn's own messages are written, so the question
        # being asked is not also in the history behind it.
        history = await repository.history_for(
            conversation.id, limit=self._settings.chat_history_messages
        )

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
            # The model that will answer, recorded on the message. A
            # deployment can offer several and a user can switch between
            # turns, so which one wrote an answer is part of the answer.
            provider_model=turn.model or getattr(self._generator, "model", None),
        )
        await session.commit()

        yield MessageStarted(id=next_id(), message_id=message.id, conversation_id=conversation.id)

        # A conversation with no library is answered by the model alone. There
        # is nothing to authorize and nothing to retrieve, and the prompt says
        # outright that the answer is unsourced.
        grounded = conversation.library_id is not None
        system_prompt = SYSTEM_PROMPT if grounded else UNGROUNDED_SYSTEM_PROMPT
        context = build_context(())

        if grounded:
            # Authorization before retrieval, and retrieval before
            # generation: a question the principal may not ask reaches
            # neither.
            try:
                scope = await self._control.library_scope(turn.principal, conversation.library_id)
            except LibraryForbidden:
                await repository.finish_message(
                    message,
                    state=MessageState.FAILED,
                    content="",
                    error_code="library_unavailable",
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

            retrieved = build_context(chunks)

            if retrieved.is_empty:
                # Nothing to ground an answer in. Saying so is the answer;
                # asking a model anyway would produce exactly the unsourced
                # prose a library was chosen to avoid. An ungrounded
                # conversation is the case where the user asked for that
                # instead, and it does not come through here.
                completed = await repository.finish_message(
                    message, state=MessageState.COMPLETED, content=NO_CONTEXT_REPLY
                )
                await session.commit()
                yield MessageDelta(id=next_id(), text=NO_CONTEXT_REPLY)
                yield MessageCompleted(id=next_id(), message=summarize_message(completed))
                return

            # Trimmed before the citations are sent, not after. A citation is
            # a claim about what the answer was written from, so emitting one
            # for a passage that then failed to fit would put a source in
            # front of the reader that the model never saw.
            context = retrieved.head(
                passages_that_fit(
                    retrieved,
                    budget=self._room_for_passages(turn, system_prompt),
                    characters_per_token=self._settings.chat_characters_per_token,
                )
            )

            if context.is_empty:
                # Retrieval worked; the window is the problem. Said plainly,
                # because "I found nothing" would send the user looking for a
                # document that is there.
                await repository.finish_message(
                    message,
                    state=MessageState.FAILED,
                    content="",
                    error_code="context_exhausted",
                )
                await session.commit()
                yield StreamError(
                    id=next_id(),
                    code="context_exhausted",
                    detail=(
                        "This question leaves no room for the passages found for it. "
                        "Ask something shorter, or choose a model with a larger context."
                    ),
                )
                return

            for index, citation in enumerate(context.citations, start=1):
                yield CitationEvent(id=next_id(), index=index, citation=citation)

        prompt = build_prompt(turn.question, context) if grounded else turn.question

        # What is left of the window after this turn's own prompt. The
        # earlier turns are what gives way: the question being asked now, and
        # the passages it is answered from, are the answer's subject.
        history = history_that_fits(
            history,
            budget=self._window(turn)
            - estimate_tokens(system_prompt, characters_per_token=self._characters_per_token)
            - estimate_tokens(prompt, characters_per_token=self._characters_per_token),
            characters_per_token=self._characters_per_token,
        )

        text = ""
        try:
            async for fragment in self._generator.stream(
                system_prompt, prompt, history=history, model=turn.model
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

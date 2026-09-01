"""Conversation and streaming routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from primer_contracts.base import WireModel
from primer_contracts.chat import ConversationSummary, Message, MessageSummary
from sqlalchemy.ext.asyncio import AsyncSession

from primer_chat.db import get_session
from primer_chat.errors import not_found
from primer_chat.identity import CurrentPrincipal
from primer_chat.repository import ChatRepository, summarize_conversation
from primer_chat.sse import encode
from primer_chat.streaming import Answering, Responder

router = APIRouter(prefix="/api/v1", tags=["chat"])

Session = Annotated[AsyncSession, Depends(get_session)]


def get_responder(request: Request) -> Responder:
    responder: Responder = request.app.state.responder
    return responder


Responding = Annotated[Responder, Depends(get_responder)]


class AskRequest(WireModel):
    """A question, and the library it is asked of, if any.

    Without a library the question is answered by the model rather than from
    the user's documents, and the answer carries no citations.
    """

    library_id: UUID | None = None
    message: Message


class FollowUpRequest(WireModel):
    message: Message


@router.get("/conversations", summary="List the caller's conversations")
async def list_conversations(
    principal: CurrentPrincipal, session: Session, library_id: UUID | None = None
) -> list[ConversationSummary]:
    conversations = await ChatRepository(session).list_conversations(
        owner_user_id=principal.user_id, library_id=library_id
    )
    return [summarize_conversation(conversation) for conversation in conversations]


@router.get("/conversations/{conversation_id}", summary="Read one conversation")
async def read_conversation(
    conversation_id: UUID, principal: CurrentPrincipal, session: Session
) -> ConversationSummary:
    conversation = await ChatRepository(session).get_conversation(
        conversation_id, owner_user_id=principal.user_id
    )
    if conversation is None:
        raise not_found("Conversation")
    return summarize_conversation(conversation)


@router.get("/conversations/{conversation_id}/messages", summary="Read a conversation's turns")
async def list_messages(
    conversation_id: UUID, principal: CurrentPrincipal, session: Session
) -> list[MessageSummary]:
    repository = ChatRepository(session)
    conversation = await repository.get_conversation(
        conversation_id, owner_user_id=principal.user_id
    )
    if conversation is None:
        raise not_found("Conversation")
    return await repository.messages_for(conversation.id)


@router.post(
    "/conversations",
    status_code=status.HTTP_200_OK,
    summary="Ask a question and stream the answer",
    response_class=StreamingResponse,
)
async def ask(
    payload: AskRequest,
    principal: CurrentPrincipal,
    session: Session,
    responder: Responding,
) -> StreamingResponse:
    """Start a conversation and stream its first answer.

    The library is authorized inside the stream rather than before it, so a
    forbidden library ends as a terminal `error` event on an open stream. A
    404 here would be equally correct; the stream is chosen so a client has
    exactly one place to handle failures.
    """
    conversation = await ChatRepository(session).create_conversation(
        library_id=payload.library_id,
        owner_user_id=principal.user_id,
        question=payload.message,
    )
    turn = Answering(principal=principal, conversation=conversation, question=payload.message)
    return stream_response(responder, session, turn)


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Continue a conversation",
    response_class=StreamingResponse,
)
async def follow_up(
    conversation_id: UUID,
    payload: FollowUpRequest,
    principal: CurrentPrincipal,
    session: Session,
    responder: Responding,
) -> StreamingResponse:
    """Ask another question in an existing conversation.

    Ownership is part of the lookup, so a stranger who knows or guesses the
    id gets the same 404 as for a conversation that does not exist - and
    gets it before Retrieval or the model is touched.
    """
    conversation = await ChatRepository(session).get_conversation(
        conversation_id, owner_user_id=principal.user_id
    )
    if conversation is None:
        raise not_found("Conversation")
    turn = Answering(principal=principal, conversation=conversation, question=payload.message)
    return stream_response(responder, session, turn)


def stream_response(
    responder: Responder, session: AsyncSession, turn: Answering
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for event in responder.respond(session, turn):
            yield encode(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Nginx and several proxies buffer responses by default, which
            # would hold every token until the answer finished and defeat
            # the point of streaming.
            "X-Accel-Buffering": "no",
        },
    )

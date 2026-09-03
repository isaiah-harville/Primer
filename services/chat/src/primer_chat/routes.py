"""Conversation and streaming routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx2
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from primer_contracts.base import WireModel
from primer_contracts.chat import (
    ChatModel,
    ChatModelList,
    ConversationSummary,
    Message,
    MessageSummary,
)
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from primer_chat.config import Settings
from primer_chat.db import get_session
from primer_chat.errors import not_found
from primer_chat.identity import CurrentPrincipal
from primer_chat.repository import ChatRepository, summarize_conversation
from primer_chat.sse import encode
from primer_chat.streaming import Answering, Responder

logger = logging.getLogger(__name__)

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
    #: One of the models this deployment offers, or none for its default.
    model: str | None = Field(default=None, max_length=200)
    message: Message


class FollowUpRequest(WireModel):
    model: str | None = Field(default=None, max_length=200)
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


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: UUID, principal: CurrentPrincipal, session: Session
) -> Response:
    """Remove a conversation and everything written in it.

    Really removed, not hidden. A conversation is what someone asked and what
    they were told, and a user who deletes one is usually deleting it for a
    reason rather than tidying a list. The messages and their citations go
    with it, by the cascade the schema already declares.

    Ownership is in the query, so another user's conversation is not found
    rather than forbidden: whether it exists is not this caller's business.
    """
    repository = ChatRepository(session)
    conversation = await repository.get_conversation(
        conversation_id, owner_user_id=principal.user_id
    )
    if conversation is None:
        raise not_found("Conversation")
    await repository.delete_conversation(conversation)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/models", summary="Models this deployment offers")
async def list_models(request: Request) -> ChatModelList:
    """What a user may choose between: everything the chat endpoint serves.

    Asked live rather than kept as a list of Primer's own, so a model added
    or removed on the endpoint shows up here without redeploying Primer to
    match.
    """
    settings: Settings = request.app.state.settings
    names = await _discover_models(settings)
    return ChatModelList(
        models=tuple(ChatModel(id=name, default=name == settings.chat_model) for name in names)
    )


async def _discover_models(settings: Settings) -> tuple[str, ...]:
    """Ask the chat endpoint what it serves, the configured default first.

    Falls back to just the configured default on any failure - unreachable,
    refused, unparsable - because a model picker that cannot be built is a
    reason to hide it, not a reason the rest of the page should fail to load.
    """
    if not settings.chat_base_url:
        return (settings.chat_model,)
    try:
        async with httpx2.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.chat_base_url.rstrip('/')}/models",
                headers={
                    "Authorization": "Bearer "
                    + (
                        settings.chat_api_key.get_secret_value()
                        if settings.chat_api_key
                        else "none"
                    )
                },
            )
        response.raise_for_status()
        served = [entry["id"] for entry in response.json().get("data", []) if entry.get("id")]
    except Exception:
        logger.warning("could not list models from %s", settings.chat_base_url, exc_info=True)
        served = []
    if not served:
        return (settings.chat_model,)
    ordered = [settings.chat_model, *served]
    return tuple(dict.fromkeys(ordered))


@router.post(
    "/conversations",
    status_code=status.HTTP_200_OK,
    summary="Ask a question and stream the answer",
    response_class=StreamingResponse,
)
async def ask(
    payload: AskRequest,
    request: Request,
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
    model = request.app.state.settings.resolve_model(payload.model)
    conversation = await ChatRepository(session).create_conversation(
        library_id=payload.library_id,
        owner_user_id=principal.user_id,
        question=payload.message,
    )
    turn = Answering(
        principal=principal,
        conversation=conversation,
        question=payload.message,
        model=model,
    )
    return stream_response(responder, session, turn)


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Continue a conversation",
    response_class=StreamingResponse,
)
async def follow_up(
    conversation_id: UUID,
    payload: FollowUpRequest,
    request: Request,
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
    turn = Answering(
        principal=principal,
        conversation=conversation,
        question=payload.message,
        model=request.app.state.settings.resolve_model(payload.model),
    )
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

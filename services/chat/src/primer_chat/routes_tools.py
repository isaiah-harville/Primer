"""Approving and denying tool calls.

Both routes are scoped to the caller's own conversations. A tool request id
is a UUID somebody could be shown or could guess, and approving another
person's pending shell command is the worst thing this service could let
happen - so ownership is part of the lookup rather than a check after it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from primer_contracts.chat import ToolCallSummary, ToolPhase
from primer_service.durable import DurableRoute
from sqlalchemy.ext.asyncio import AsyncSession

from primer_chat.db import get_session
from primer_chat.errors import ProblemError, not_found
from primer_chat.identity import CurrentPrincipal
from primer_chat.tool_repository import ToolRepository, summarize_call

router = APIRouter(prefix="/api/v1/tool-requests", tags=["tools"], route_class=DurableRoute)

Session = Annotated[AsyncSession, Depends(get_session)]


def already_decided(phase: ToolPhase) -> ProblemError:
    """A decided request keeps its first decision.

    Reported rather than silently ignored: a user pressing approve on a
    request that expired while they read it deserves to know that is what
    happened, not to watch nothing occur.
    """
    from primer_contracts.errors import ErrorCode

    return ProblemError(
        code=ErrorCode.CONFLICT,
        title="Already decided",
        status_code=status.HTTP_409_CONFLICT,
        detail=f"This request is already {phase.value} and cannot be changed.",
    )


@router.get("", summary="List pending tool requests")
async def list_requests(
    principal: CurrentPrincipal, session: Session, conversation_id: UUID | None = None
) -> list[ToolCallSummary]:
    calls = await ToolRepository(session).pending_for(
        owner_user_id=principal.user_id, conversation_id=conversation_id
    )
    return [summarize_call(call) for call in calls]


@router.post("/{request_id}/approve", summary="Approve a tool call")
async def approve(
    request_id: UUID, principal: CurrentPrincipal, session: Session
) -> ToolCallSummary:
    return await decide(request_id, principal.subject, principal.user_id, session, approved=True)


@router.post("/{request_id}/deny", summary="Deny a tool call")
async def deny(request_id: UUID, principal: CurrentPrincipal, session: Session) -> ToolCallSummary:
    return await decide(request_id, principal.subject, principal.user_id, session, approved=False)


async def decide(
    request_id: UUID,
    actor: str,
    owner_user_id: UUID,
    session: AsyncSession,
    *,
    approved: bool,
) -> ToolCallSummary:
    repository = ToolRepository(session)
    call = await repository.get(request_id, owner_user_id=owner_user_id)
    if call is None:
        raise not_found("Tool request")

    decided = await repository.decide(call, actor=actor, approved=approved)
    if decided is None:
        raise already_decided(ToolPhase(call.phase))
    return summarize_call(decided)

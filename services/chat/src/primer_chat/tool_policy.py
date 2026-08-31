"""Deciding whether a tool call may run.

Gates are evaluated in a fixed order, and the first failure is the answer.
The order is not arbitrary: it goes from the broadest, cheapest, most
operator-controlled check to the narrowest and most user-specific, so a
deployment with tools switched off never consults a group list, and a tool
nobody allowed never reaches a capability check.

Every path that is not an explicit allow is a deny. There is no default
branch that permits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from primer_contracts.identity import Principal

from primer_chat.tool_config import ToolConfiguration, is_execution_tool


class DenialReason(StrEnum):
    """Why a call was refused. Stable, because the UI explains each one."""

    TOOLS_DISABLED = "tools_disabled"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    GROUP_NOT_ENTITLED = "group_not_entitled"
    MODEL_INCOMPATIBLE = "model_incompatible"
    SANDBOX_UNDECLARED = "sandbox_undeclared"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ToolDecision:
    """Whether the tool may be offered, and what still stands in the way."""

    allowed: bool
    reason: DenialReason | None = None
    #: True when the user must approve before this runs. Every tool that
    #: passes the gates still needs approval: passing means "may be asked
    #: for", not "may run".
    requires_approval: bool = True
    server: str | None = None


class ToolPolicy:
    """Evaluates the gates. Holds no state; decisions are pure."""

    def __init__(self, configuration: ToolConfiguration, *, model_supports_tools: bool) -> None:
        self._configuration = configuration
        self._model_supports_tools = model_supports_tools

    def evaluate(self, principal: Principal, tool_name: str) -> ToolDecision:
        """Decide in a fixed order, cheapest and broadest gate first."""
        if not self._configuration.enabled:
            return ToolDecision(allowed=False, reason=DenialReason.TOOLS_DISABLED)

        server = self._configuration.server_for(tool_name)
        if server is None:
            # Not on any allowlist. An unknown tool is refused rather than
            # investigated: a server that gains a tool in a later release
            # must not gain the right to run it here.
            return ToolDecision(allowed=False, reason=DenialReason.TOOL_NOT_ALLOWED)

        if server.required_groups and not set(server.required_groups) & set(principal.groups):
            return ToolDecision(
                allowed=False, reason=DenialReason.GROUP_NOT_ENTITLED, server=server.name
            )

        if not self._model_supports_tools:
            # The model cannot emit a tool call, so offering it would produce
            # a feature that silently never fires.
            return ToolDecision(
                allowed=False, reason=DenialReason.MODEL_INCOMPATIBLE, server=server.name
            )

        if is_execution_tool(tool_name) and (
            server.sandbox is None or not server.sandbox.is_complete
        ):
            # Belt and braces: configuration loading refuses this too. The
            # check is repeated because it is the one whose absence would be
            # a stranger running code on somebody's infrastructure.
            return ToolDecision(
                allowed=False, reason=DenialReason.SANDBOX_UNDECLARED, server=server.name
            )

        return ToolDecision(allowed=True, requires_approval=True, server=server.name)


@dataclass
class ToolRequest:
    """A pending call, waiting for a person to decide.

    Approval is consent to one action at one moment. It expires, it cannot
    be given twice, and it cannot be given for a call that was already
    denied or cancelled - each of which is a separate test.
    """

    id: UUID
    conversation_id: UUID
    tool_name: str
    arguments: dict[str, object]
    state: ApprovalState
    requested_at: datetime
    ttl_seconds: int
    decided_at: datetime | None = None
    decided_by: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        return moment >= self.requested_at + timedelta(seconds=self.ttl_seconds)

    def approve(self, actor: str, now: datetime | None = None) -> ApprovalState:
        return self._decide(ApprovalState.APPROVED, actor, now)

    def deny(self, actor: str, now: datetime | None = None) -> ApprovalState:
        return self._decide(ApprovalState.DENIED, actor, now)

    def cancel(self, now: datetime | None = None) -> ApprovalState:
        return self._decide(ApprovalState.CANCELLED, actor=None, now=now)

    def _decide(
        self, target: ApprovalState, actor: str | None, now: datetime | None
    ) -> ApprovalState:
        """Apply a decision, if one is still possible.

        A decided request keeps its first decision. Re-approving is not a
        no-op that quietly re-arms the call: the state is returned unchanged
        so the caller can see nothing happened.
        """
        moment = now or datetime.now(UTC)
        if self.state is not ApprovalState.PENDING:
            return self.state
        if self.is_expired(moment):
            self.state = ApprovalState.EXPIRED
            return self.state
        self.state = target
        self.decided_at = moment
        self.decided_by = actor
        return self.state

    def may_run(self, now: datetime | None = None) -> bool:
        """The single question the runner asks before invoking anything."""
        return self.state is ApprovalState.APPROVED and not self.is_expired(now)

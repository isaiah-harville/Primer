"""Deny by default, in a fixed order, with approval that expires.

Every test here is about something *not* running. That is the whole point of
the module: the failure mode it guards against is a stranger's document
persuading a model to run a command on somebody's infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from primer_chat.tool_config import (
    SandboxDeclaration,
    ToolConfiguration,
    ToolServer,
    is_execution_tool,
)
from primer_chat.tool_policy import ApprovalState, DenialReason, ToolPolicy, ToolRequest
from primer_contracts.identity import Principal
from pydantic import ValidationError


def complete_sandbox() -> SandboxDeclaration:
    return SandboxDeclaration(
        ephemeral_per_session=True,
        network_disabled_by_default=True,
        no_host_mounts=True,
        no_host_socket=True,
        no_application_secrets=True,
        runs_as_non_root=True,
        cpu_limited=True,
        memory_limited=True,
        disk_limited=True,
        process_limited=True,
        time_limited=True,
        output_limited=True,
    )


def principal(groups: tuple[str, ...] = ()) -> Principal:
    return Principal(
        subject="asker", user_id=uuid.uuid5(uuid.NAMESPACE_URL, "asker"), groups=groups
    )


def configuration(
    *, enabled: bool = True, groups: tuple[str, ...] = (), with_sandbox: bool = True
) -> ToolConfiguration:
    return ToolConfiguration(
        enabled=enabled,
        servers=(
            ToolServer(
                name="sandbox",
                url="http://mcp:9000",
                allowed_tools=("sandbox.shell",),
                required_groups=groups,
                sandbox=complete_sandbox() if with_sandbox else None,
            ),
        ),
    )


def policy(
    *,
    model_supports_tools: bool = True,
    enabled: bool = True,
    groups: tuple[str, ...] = (),
    with_sandbox: bool = True,
) -> ToolPolicy:
    """Spelled out rather than **kwargs, so the arguments stay type-checked."""
    return ToolPolicy(
        configuration(enabled=enabled, groups=groups, with_sandbox=with_sandbox),
        model_supports_tools=model_supports_tools,
    )


def test_shell_requires_every_gate() -> None:
    """The plan's case: with tools off, nothing else is even consulted."""
    decision = policy(enabled=False).evaluate(principal(), "sandbox.shell")

    assert decision.allowed is False
    assert decision.reason is DenialReason.TOOLS_DISABLED


def test_a_tool_nobody_allowed_is_refused() -> None:
    """An allowlist, so a server gaining a tool does not gain the right to run it."""
    decision = policy().evaluate(principal(), "sandbox.rm_rf")

    assert decision.allowed is False
    assert decision.reason is DenialReason.TOOL_NOT_ALLOWED


def test_a_user_outside_the_entitled_group_is_refused() -> None:
    decision = policy(groups=("operators",)).evaluate(principal(), "sandbox.shell")

    assert decision.allowed is False
    assert decision.reason is DenialReason.GROUP_NOT_ENTITLED


def test_a_user_inside_the_entitled_group_passes_that_gate() -> None:
    decision = policy(groups=("operators",)).evaluate(
        principal(groups=("operators", "staff")), "sandbox.shell"
    )
    assert decision.allowed is True


def test_a_model_that_cannot_call_tools_removes_the_capability() -> None:
    """Offering it would produce a feature that silently never fires."""
    decision = policy(model_supports_tools=False).evaluate(principal(), "sandbox.shell")

    assert decision.allowed is False
    assert decision.reason is DenialReason.MODEL_INCOMPATIBLE


def test_gates_are_evaluated_broadest_first() -> None:
    """A disabled deployment reports that, not a group problem it also has."""
    decision = ToolPolicy(
        configuration(enabled=False, groups=("operators",)), model_supports_tools=False
    ).evaluate(principal(), "sandbox.shell")

    assert decision.reason is DenialReason.TOOLS_DISABLED


def test_passing_the_gates_still_requires_approval() -> None:
    """Allowed means 'may be asked for', never 'may run'."""
    decision = policy().evaluate(principal(), "sandbox.shell")

    assert decision.allowed is True
    assert decision.requires_approval is True


def test_execution_tools_without_a_sandbox_are_refused_at_configuration() -> None:
    """A deployment that would refuse every call at runtime is wrong now."""
    with pytest.raises(ValidationError):
        ToolServer(name="s", url="http://mcp", allowed_tools=("sandbox.shell",))


def test_a_half_filled_sandbox_declaration_is_not_a_declaration() -> None:
    """Every field defaults to unsafe, so omission cannot pass for consent."""
    partial = SandboxDeclaration(ephemeral_per_session=True, no_host_mounts=True)

    assert partial.is_complete is False
    with pytest.raises(ValidationError):
        ToolServer(name="s", url="http://mcp", allowed_tools=("sandbox.shell",), sandbox=partial)


def test_the_missing_guarantees_are_named() -> None:
    """An operator needs to know which promise they have not made."""
    missing = SandboxDeclaration(ephemeral_per_session=True).missing()

    assert "no_host_mounts" in missing
    assert "runs_as_non_root" in missing
    assert "ephemeral_per_session" not in missing


@pytest.mark.parametrize(
    "name",
    ["sandbox.shell", "exec.run", "code.interpreter", "python.eval", "bash", "tools/shell.run"],
)
def test_execution_tools_are_recognised_broadly(name: str) -> None:
    """Over-matching costs a declaration; under-matching runs code unsandboxed."""
    assert is_execution_tool(name) is True


@pytest.mark.parametrize("name", ["search.web", "docs.lookup", "calendar.read"])
def test_ordinary_tools_are_not_treated_as_execution(name: str) -> None:
    assert is_execution_tool(name) is False


def request_now(ttl: int = 300) -> ToolRequest:
    return ToolRequest(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        tool_name="sandbox.shell",
        arguments={"command": "ls"},
        state=ApprovalState.PENDING,
        requested_at=datetime.now(UTC),
        ttl_seconds=ttl,
    )


def test_a_pending_request_may_not_run() -> None:
    assert request_now().may_run() is False


def test_an_approved_request_may_run() -> None:
    pending = request_now()
    assert pending.approve("asker") is ApprovalState.APPROVED
    assert pending.may_run() is True


def test_a_denied_request_may_not_run() -> None:
    pending = request_now()
    pending.deny("asker")
    assert pending.may_run() is False


def test_approving_twice_does_not_re_arm_a_call() -> None:
    """A decided request keeps its first decision."""
    pending = request_now()
    pending.deny("asker")

    assert pending.approve("asker") is ApprovalState.DENIED
    assert pending.may_run() is False


def test_an_expired_request_cannot_be_approved() -> None:
    """Approval is consent to one action at one moment."""
    stale = request_now(ttl=60)
    stale.requested_at = datetime.now(UTC) - timedelta(seconds=120)

    assert stale.approve("asker") is ApprovalState.EXPIRED
    assert stale.may_run() is False


def test_an_approval_that_expires_before_it_runs_is_not_honoured() -> None:
    """The runner re-checks; approval is not a token that stays valid."""
    approved = request_now(ttl=60)
    approved.approve("asker")

    assert approved.may_run(datetime.now(UTC) + timedelta(seconds=120)) is False


def test_a_cancelled_request_cannot_later_be_approved() -> None:
    pending = request_now()
    pending.cancel()

    assert pending.approve("asker") is ApprovalState.CANCELLED
    assert pending.may_run() is False


def test_the_deciding_actor_is_recorded() -> None:
    """Every decision has an actor, because the audit row needs one."""
    pending = request_now()
    pending.approve("asker")

    assert pending.decided_by == "asker"
    assert pending.decided_at is not None

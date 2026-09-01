"""Running an approved call, and refusing everything else.

The runner is the last thing before something executes, so every refusal it
makes is one a person is relying on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from primer_chat.tool_config import ToolConfiguration
from primer_chat.tool_policy import ApprovalState, ToolPolicy, ToolRequest
from primer_chat.tool_runner import (
    MAX_ARGUMENT_CHARS,
    MAX_OUTPUT_CHARS,
    ToolRunner,
    sanitize_arguments,
    truncate,
)
from primer_contracts.chat import ToolPhase


class RecordingInvoker:
    def __init__(self, output: str = "ok", fail: bool = False) -> None:
        self.output = output
        self.fail = fail
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke(self, tool_name: str, arguments: dict[str, object]) -> str:
        self.calls.append((tool_name, arguments))
        if self.fail:
            raise RuntimeError("connection string postgres://user:hunter2@db")
        return self.output


def request(state: ApprovalState = ApprovalState.APPROVED, ttl: int = 300) -> ToolRequest:
    return ToolRequest(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        tool_name="sandbox.shell",
        arguments={"command": "ls"},
        state=state,
        requested_at=datetime.now(UTC),
        ttl_seconds=ttl,
    )


def runner(invoker: RecordingInvoker | None = None) -> ToolRunner:
    configuration = ToolConfiguration(enabled=True)
    return ToolRunner(
        configuration,
        ToolPolicy(configuration, model_supports_tools=True),
        invoker=invoker,
    )


def test_an_approved_call_runs() -> None:
    invoker = RecordingInvoker(output="total 0")
    outcome = runner(invoker).run(request())

    assert outcome.phase is ToolPhase.COMPLETED
    assert outcome.output == "total 0"
    assert invoker.calls == [("sandbox.shell", {"command": "ls"})]


def test_a_pending_call_does_not_run() -> None:
    invoker = RecordingInvoker()
    outcome = runner(invoker).run(request(state=ApprovalState.PENDING))

    assert outcome.phase is ToolPhase.DENIED
    assert outcome.error_code == "not_approved"
    assert invoker.calls == []


def test_a_denied_call_does_not_run() -> None:
    invoker = RecordingInvoker()
    outcome = runner(invoker).run(request(state=ApprovalState.DENIED))

    assert outcome.phase is ToolPhase.DENIED
    assert invoker.calls == []


def test_an_approval_that_expired_before_running_is_refused() -> None:
    """The gap between deciding and running is exactly where this matters."""
    invoker = RecordingInvoker()
    stale = request(ttl=60)
    stale.requested_at = datetime.now(UTC) - timedelta(seconds=120)

    outcome = runner(invoker).run(stale)

    assert outcome.phase is ToolPhase.EXPIRED
    assert outcome.error_code == "approval_expired"
    assert invoker.calls == []


def test_no_mcp_connection_is_a_deployment_fault_not_a_refusal() -> None:
    """Reporting it as denied would blame the user for a missing service."""
    outcome = runner(invoker=None).run(request())

    assert outcome.phase is ToolPhase.FAILED
    assert outcome.error_code == "tools_unavailable"


def test_a_failing_tool_reports_a_stable_code_and_no_internals() -> None:
    """A tool's error message can contain anything the tool chose to print."""
    outcome = runner(RecordingInvoker(fail=True)).run(request())

    assert outcome.phase is ToolPhase.FAILED
    assert outcome.error_code == "tool_failed"
    assert "hunter2" not in str(outcome)


def test_output_is_bounded() -> None:
    """Untrusted text from a process Primer does not control."""
    outcome = runner(RecordingInvoker(output="x" * (MAX_OUTPUT_CHARS + 500))).run(request())

    assert outcome.output is not None
    assert len(outcome.output) < MAX_OUTPUT_CHARS + 100
    assert outcome.output.endswith("(output truncated)")


def test_short_output_is_untouched() -> None:
    assert truncate("brief") == "brief"


def test_arguments_are_truncated_rather_than_redacted() -> None:
    """A user has to see the command they are approving."""
    sanitized = sanitize_arguments({"command": "echo " + "a" * (MAX_ARGUMENT_CHARS + 100)})

    assert sanitized["command"].startswith("echo aaa")
    assert sanitized["command"].endswith("(truncated)")


def test_short_arguments_pass_through_unchanged() -> None:
    assert sanitize_arguments({"command": "ls -la", "timeout": 30}) == {
        "command": "ls -la",
        "timeout": 30,
    }


def test_a_completed_call_reports_how_long_it_took() -> None:
    outcome = runner(RecordingInvoker()).run(request())
    assert outcome.duration_ms is not None
    assert outcome.duration_ms >= 0

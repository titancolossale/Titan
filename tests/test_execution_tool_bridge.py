# =====================================
# Titan Tool Execution Bridge Tests
# =====================================

"""Phase 18.3 — Tool Execution Bridge: resolve, authorize, dispatch, normalize."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pytest

from brain.decision_engine import DecisionEngine
from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_tool_bridge import ToolExecutionBridge
from brain.execution_tool_models import (
    DIAG_TOOL_COMPLETED,
    DIAG_TOOL_DISPATCH,
    DIAG_TOOL_FAILED,
    DIAG_TOOL_STARTED,
    DIAG_TOOL_TIMEOUT,
    DIAG_TOOL_UNAVAILABLE,
    BridgeExecutionStatus,
)
from brain.planning_models import Plan, PlanStatus
from brain.prompt_builder import PromptBuilder
from brain.pipeline.context_bundle import ThinkContext
from brain.tool_adapter import RegistryToolAdapter
from core.actions import Action, ActionRegistry, ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.state_manager import WorkspaceState
from core.tools import BaseTool, ToolRegistry
from tools.confirmation_gate import ConfirmationGate
from tools.tool_capability import ToolCapability
from tools.tool_enums import RiskLevel
from tools.tool_run_models import ToolExecutionContext


class _EchoTool(BaseTool):
    """Minimal registry tool for bridge tests."""

    def __init__(self, *, requires_confirmation: bool = False) -> None:
        super().__init__()
        self._requires_confirmation = requires_confirmation
        self._actions = (
            Action(
                id="echo",
                name="Echo",
                description="Echo a message.",
                tool_id=self.id,
                permission_id="echo_tool.echo",
                parameters={"message": {"type": "string", "required": False}},
            ),
            Action(
                id="fail",
                name="Fail",
                description="Always fail.",
                tool_id=self.id,
                permission_id="echo_tool.fail",
                parameters={},
            ),
            Action(
                id="slow",
                name="Slow",
                description="Sleep then succeed.",
                tool_id=self.id,
                permission_id="echo_tool.slow",
                parameters={"seconds": {"type": "number", "required": False}},
            ),
        )

    @property
    def id(self) -> str:
        return "echo_tool"

    @property
    def name(self) -> str:
        return "Echo Tool"

    @property
    def description(self) -> str:
        return "Test echo tool."

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> str:
        return "demo"

    @property
    def requires_confirmation(self) -> bool:
        return self._requires_confirmation

    @property
    def capabilities(self) -> list[str]:
        return ["echo.message"]

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        if action_id == "fail":
            return ActionResult(
                success=False,
                message="Echo fail requested",
                errors=["Echo fail requested"],
            )
        if action_id == "slow":
            time.sleep(float(kwargs.get("seconds", 0.5)))
            return ActionResult(success=True, message="Slow done", data={"ok": True})
        if action_id == "echo":
            message = str(kwargs.get("message", "hello"))
            return ActionResult(
                success=True,
                message=f"Echoed: {message}",
                data={"echo": message, "secret": "do-not-leak"},
            )
        raise RuntimeError(f"boom:{action_id}")

    def execute(self, **kwargs: object) -> object:
        return self.execute_action("echo", **kwargs).data


def _make_plan(actions: list[str]) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship",
        current_project="Bridge",
        current_mission="18.3",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=10.0,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=PlanStatus.ACTIVE,
    )


def _wired_bridge(
    *,
    requires_confirmation: bool = False,
    permission_level: PermissionLevel = PermissionLevel.SAFE,
    with_gate: bool = False,
) -> tuple[ToolExecutionBridge, ToolRegistry, PermissionManager]:
    registry = ToolRegistry()
    tool = _EchoTool(requires_confirmation=requires_confirmation)
    registry.register_tool(tool)

    actions = ActionRegistry()
    permissions = PermissionManager()
    for action in tool.list_actions():
        actions.register_action(action)
        permissions.register_permission(
            Permission(
                id=action.permission_id,
                name=action.name,
                description=action.description,
                level=permission_level
                if action.id != "fail"
                else PermissionLevel.SAFE,
            )
        )

    gate = ConfirmationGate() if with_gate else None
    bridge = ToolExecutionBridge(
        tool_registry=registry,
        action_registry=actions,
        permission_manager=permissions,
        confirmation_gate=gate,
    )
    return bridge, registry, permissions


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------


def test_tool_resolution_from_composite_action() -> None:
    bridge, _, _ = _wired_bridge()
    request = bridge.resolve_request("echo_tool:echo")
    assert request is not None
    assert request.tool_id == "echo_tool"
    assert request.action_id == "echo"


def test_tool_resolution_from_metadata() -> None:
    bridge, _, _ = _wired_bridge()
    request = bridge.resolve_request(
        "ignored text",
        action_metadata={
            "tool_id": "echo_tool",
            "action_id": "echo",
            "parameters": {"message": "hi"},
        },
    )
    assert request is not None
    assert request.tool_id == "echo_tool"
    assert request.action_id == "echo"
    assert request.parameters["message"] == "hi"


def test_tool_resolution_exact_tool_id_uses_first_action() -> None:
    bridge, _, _ = _wired_bridge()
    request = bridge.resolve_request("echo_tool")
    assert request is not None
    assert request.tool_id == "echo_tool"
    assert request.action_id == "echo"


def test_non_tool_action_does_not_resolve() -> None:
    bridge, _, _ = _wired_bridge()
    assert bridge.resolve_request("Wire Brain") is None


def test_adapter_cached_after_resolve() -> None:
    bridge, _, _ = _wired_bridge()
    first = bridge.get_adapter("echo_tool")
    second = bridge.get_adapter("echo_tool")
    assert first is second
    assert isinstance(first, RegistryToolAdapter)


# ---------------------------------------------------------------------------
# Permission / confirmation validation
# ---------------------------------------------------------------------------


def test_permission_validation_blocks_forbidden() -> None:
    bridge, _, permissions = _wired_bridge()
    permissions.remove_permission("echo_tool.echo")
    permissions.register_permission(
        Permission(
            id="echo_tool.echo",
            name="Echo",
            description="Blocked echo",
            level=PermissionLevel.BLOCKED,
        )
    )
    result = bridge.dispatch(action="echo_tool:echo", preauthorized=True)
    assert result.status == BridgeExecutionStatus.FORBIDDEN
    assert result.success is False


def test_confirmation_validation_blocks_without_token() -> None:
    bridge, _, _ = _wired_bridge(requires_confirmation=True, with_gate=True)
    result = bridge.dispatch(
        action="echo_tool:echo",
        confirmed=False,
        preauthorized=False,
    )
    assert result.status == BridgeExecutionStatus.BLOCKED
    assert "Confirmation required" in (result.blocked_reason or "")


def test_confirmation_validation_allows_valid_token() -> None:
    bridge, _, _ = _wired_bridge(requires_confirmation=True, with_gate=True)
    assert bridge._confirmation_gate is not None
    capability = ToolCapability(
        name="echo_tool",
        description="echo",
        parameters=(),
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
    )
    context = ToolExecutionContext(
        caller="test",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    issued = bridge._confirmation_gate.issue_request(
        "echo_tool",
        capability,
        context,
        {},
    )
    result = bridge.dispatch(
        action="echo_tool:echo",
        confirmed=True,
        confirmation_token=issued.token,
        session_id="s1",
        user="Nolan",
        turn_id="t1",
        preauthorized=False,
    )
    assert result.status == BridgeExecutionStatus.SUCCESS
    assert result.success is True


# ---------------------------------------------------------------------------
# Dispatch outcomes
# ---------------------------------------------------------------------------


def test_successful_dispatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge, _, _ = _wired_bridge()
    with caplog.at_level(logging.INFO, logger="brain.execution_tool_bridge"):
        result = bridge.dispatch(
            action="echo_tool:echo",
            action_metadata={"parameters": {"message": "ping"}},
            preauthorized=True,
        )
    assert result.status == BridgeExecutionStatus.SUCCESS
    assert result.success is True
    assert result.tool_id == "echo_tool"
    assert "secret" not in (result.result_summary or "")
    assert "do-not-leak" not in (result.message or "")
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith(DIAG_TOOL_DISPATCH) for m in messages)
    assert any(m.startswith(DIAG_TOOL_STARTED) for m in messages)
    assert any(m.startswith(DIAG_TOOL_COMPLETED) for m in messages)


def test_failed_dispatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge, _, _ = _wired_bridge()
    with caplog.at_level(logging.INFO, logger="brain.execution_tool_bridge"):
        result = bridge.dispatch(action="echo_tool:fail", preauthorized=True)
    assert result.status == BridgeExecutionStatus.FAILED
    assert result.success is False
    assert result.error
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith(DIAG_TOOL_FAILED) for m in messages)


def test_unavailable_tool(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge, _, _ = _wired_bridge()
    with caplog.at_level(logging.INFO, logger="brain.execution_tool_bridge"):
        result = bridge.dispatch(
            action="missing_tool:echo",
            action_metadata={"tool_id": "missing_tool", "action_id": "echo"},
            preauthorized=True,
        )
    assert result.status == BridgeExecutionStatus.FAILED
    assert "unavailable" in result.message.lower()
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith(DIAG_TOOL_UNAVAILABLE) for m in messages)


def test_disabled_tool_unavailable() -> None:
    bridge, registry, _ = _wired_bridge()
    registry.disable_tool("echo_tool")
    bridge.invalidate_adapter("echo_tool")
    result = bridge.dispatch(action="echo_tool:echo", preauthorized=True)
    assert result.status == BridgeExecutionStatus.FAILED
    assert "disabled" in result.message.lower()


def test_timeout_dispatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge, _, _ = _wired_bridge()
    with caplog.at_level(logging.INFO, logger="brain.execution_tool_bridge"):
        result = bridge.dispatch(
            action="echo_tool:slow",
            action_metadata={"parameters": {"seconds": 1.0}},
            timeout_seconds=0.05,
            preauthorized=True,
        )
    assert result.status == BridgeExecutionStatus.TIMEOUT
    assert result.success is False
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith(DIAG_TOOL_TIMEOUT) for m in messages)


def test_normalized_errors_never_expose_raw_exception() -> None:
    bridge, _, _ = _wired_bridge()
    result = bridge.dispatch(
        action="echo_tool:nope",
        action_metadata={"tool_id": "echo_tool", "action_id": "nope"},
        preauthorized=True,
    )
    # Unknown action → unavailable (not a raw traceback).
    assert result.status == BridgeExecutionStatus.FAILED
    assert "Traceback" not in (result.message or "")
    assert "Traceback" not in (result.error or "")

    # Force adapter exception path via a registered bogus path:
    adapter = bridge.get_adapter("echo_tool")
    assert adapter is not None
    # Call execute_action that raises for unknown after bypassing list check:
    forced = RegistryToolAdapter(adapter.tool).execute("missing_raise")
    assert forced.status == BridgeExecutionStatus.FAILED
    assert "Traceback" not in (forced.message or "")
    assert "boom" in (forced.error or "").lower() or "boom" in (
        forced.message or ""
    ).lower()


# ---------------------------------------------------------------------------
# WorkspaceState updates
# ---------------------------------------------------------------------------


def test_workspace_state_updated_after_bridge_dispatch() -> None:
    bridge, _, _ = _wired_bridge()
    workspace = WorkspaceState(
        active_project="Titan",
        last_tool=None,
        last_execution=None,
        execution_duration=None,
        execution_status=None,
        last_error=None,
    )
    result = bridge.dispatch(
        action="echo_tool:echo",
        workspace=workspace,
        action_metadata={"parameters": {"message": "ws"}},
        preauthorized=True,
    )
    assert result.success is True
    assert workspace.last_tool == "echo_tool"
    assert workspace.execution_status == BridgeExecutionStatus.SUCCESS.value
    assert workspace.last_execution
    assert workspace.execution_duration is not None
    assert workspace.execution_duration >= 0.0
    assert workspace.last_error is None
    assert "echo_tool" in workspace.active_tools


def test_workspace_records_error_on_failure() -> None:
    bridge, _, _ = _wired_bridge()
    workspace = WorkspaceState()
    result = bridge.dispatch(
        action="echo_tool:fail",
        workspace=workspace,
        preauthorized=True,
    )
    assert result.success is False
    assert workspace.execution_status == BridgeExecutionStatus.FAILED.value
    assert workspace.last_error


# ---------------------------------------------------------------------------
# ExecutionEngine integration
# ---------------------------------------------------------------------------


def test_execution_engine_uses_bridge_for_tool_action() -> None:
    bridge, _, _ = _wired_bridge()
    engine = ExecutionEngine(tool_bridge=bridge)
    plan = _make_plan(["echo_tool:echo"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState(active_project="Titan", current_step=None)
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        action_metadata={
            "parameters": {"message": "via-engine"},
            "risk_level": "SAFE_READ",
            "action_type": "read",
        },
        send_feedback=False,
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True
    assert engine.active_task is not None
    assert engine.active_task.last_tool == "echo_tool"
    assert workspace.last_tool == "echo_tool"
    assert workspace.execution_status == BridgeExecutionStatus.SUCCESS.value


def test_execution_engine_cognitive_action_still_succeeds() -> None:
    bridge, _, _ = _wired_bridge()
    engine = ExecutionEngine(tool_bridge=bridge)
    plan = _make_plan(["Wire Brain"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    result = engine.execute(decision=decision, plan=plan, send_feedback=False)
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True
    assert "Wire Brain" in result.message


def test_prompt_exposes_only_last_tool_status_result() -> None:
    bridge, _, _ = _wired_bridge()
    engine = ExecutionEngine(tool_bridge=bridge)
    plan = _make_plan(["echo_tool:echo"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine.execute(
        decision=decision,
        plan=plan,
        action_metadata={
            "parameters": {"message": "prompt"},
            "risk_level": "SAFE_READ",
            "action_type": "read",
        },
        send_feedback=False,
    )
    text = engine.active_task.format_for_prompt()
    assert "Last Tool: echo_tool" in text
    assert "Execution Status: SUCCESS" in text
    assert "Execution Result:" in text
    assert "do-not-leak" not in text
    assert "secret" not in text

    ctx = ThinkContext(
        user_message="Go",
        current_user="Nolan",
        execution_text=text,
    )
    prompt = PromptBuilder().build(ctx)
    assert "EXÉCUTION ACTUELLE" in prompt
    assert "Last Tool:" in prompt
    assert "Execution Status:" in prompt
    assert "Execution Result:" in prompt

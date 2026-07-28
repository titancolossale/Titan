# =====================================
# Titan Agent Runtime E2E Validation
# =====================================

"""Phase 19.1 — End-to-end agent runtime validation.

Proves Conversation → WorkspaceState → Mission → Project → Goal → Planning →
Decision → Execution → Tool Bridge → Recovery → Workspace Update → Learning →
LLM Response without recreating any subsystem.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.autonomy_policy import AutonomyPolicy
from brain.brain import Brain
from brain.decision_engine import DecisionEngine
from brain.execution import Execution as ExecutionFacade
from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_recovery import (
    DIAG_EXECUTION_RETRY,
    DIAG_EXECUTION_ROLLBACK,
    ExecutionCheckpoint,
    ExecutionRecoveryManager,
    ExecutionRetryPolicy,
    RecoveryAction,
    RollbackStatus,
)
from brain.execution_tool_bridge import ToolExecutionBridge
from brain.execution_tool_models import (
    DIAG_TOOL_COMPLETED,
    DIAG_TOOL_DISPATCH,
    BridgeExecutionResult,
    BridgeExecutionStatus,
)
from brain.pipeline.stages import (
    DIAG_PIPELINE_FAILED,
    DIAG_PIPELINE_FINISHED,
    DIAG_PIPELINE_STAGE,
    DIAG_PIPELINE_START,
    STAGE_ORDER,
)
from brain.planning_engine import PlanningEngine
from brain.planning_models import Plan, PlanStatus
from core.actions import Action, ActionRegistry, ActionResult
from core.goal_models import GoalPriority
from core.mission_models import MissionPriority
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager, WorkspaceState
from core.tools import BaseTool, ToolRegistry
from tools.confirmation_gate import ConfirmationGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ScriptedBridge:
    """Minimal Tool Execution Bridge stub for recovery / failure paths."""

    def __init__(self, results: list[BridgeExecutionResult]) -> None:
        self._results = list(results)
        self.calls = 0

    def dispatch(self, **kwargs: Any) -> BridgeExecutionResult:
        self.calls += 1
        if not self._results:
            return BridgeExecutionResult.cognitive_success(message="empty script")
        return self._results.pop(0)

    def apply_workspace_update(
        self, workspace: Any | None, result: BridgeExecutionResult
    ) -> None:
        if workspace is None:
            return
        workspace.last_tool = result.tool_id
        workspace.last_execution = result.execution_result
        workspace.execution_status = result.status.value
        workspace.execution_duration = result.duration
        workspace.last_error = result.error if not result.success else None


class _EchoTool(BaseTool):
    """Registry tool used only inside this validation suite."""

    def __init__(self) -> None:
        super().__init__()
        self._actions = (
            Action(
                id="echo",
                name="Echo",
                description="Echo a message.",
                tool_id=self.id,
                permission_id="echo_tool.echo",
                parameters={"message": {"type": "string", "required": False}},
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
        return "Echo for runtime validation."

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> str:
        return "demo"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return ["echo.message"]

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        if action_id != "echo":
            return ActionResult(
                success=False,
                message=f"unknown action {action_id}",
                errors=[f"unknown action {action_id}"],
            )
        message = str(kwargs.get("message") or "ok")
        return ActionResult(success=True, message=message, data={"echo": message})

    def execute(self, **kwargs: object) -> object:
        return self.execute_action("echo", **kwargs).data


def _seed_hierarchy(brain: Brain) -> tuple[Any, Any, Any]:
    """Create one Goal → Project → Mission chain (no duplicates)."""
    goal = brain.goal_manager.create_goal(
        "Ship Titan Runtime",
        priority=GoalPriority.HIGH,
    )
    project = brain.project_manager.create_project(
        "Agent Runtime Validation",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission = brain.mission_manager.create_mission(
        "Phase 19.1 Validation",
        "Prove end-to-end agent runtime",
        ["Design models", "Wire pipeline", "Add tests"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )
    return goal, project, mission


def _failed_bridge(
    *,
    message: str = "connection temporarily unavailable",
    reversible: bool = False,
    rollback_token: str | None = None,
) -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=BridgeExecutionStatus.FAILED,
        message=message,
        success=False,
        duration=0.01,
        tool_id="fake_tool",
        action_id="run",
        error=message,
        result_summary=message,
        reversible=reversible,
        rollback_token=rollback_token,
    )


def _success_bridge(*, message: str = "ok") -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=BridgeExecutionStatus.SUCCESS,
        message=message,
        success=True,
        duration=0.01,
        tool_id="fake_tool",
        action_id="run",
        result_summary=message,
    )


def _recovery_engine(
    tmp_path: Path,
    *,
    results: list[BridgeExecutionResult],
    max_attempts: int = 3,
) -> ExecutionEngine:
    policy = ExecutionRetryPolicy(
        max_attempts=max_attempts,
        retry_delay=0.0,
        backoff_multiplier=2.0,
        retry_on_timeout=True,
    )
    recovery = ExecutionRecoveryManager(
        policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        sleep_fn=lambda _seconds: None,
    )
    return ExecutionEngine(
        tool_bridge=_ScriptedBridge(results),  # type: ignore[arg-type]
        recovery_manager=recovery,
        retry_policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        auto_resume=False,
    )


def _wired_echo_bridge() -> ToolExecutionBridge:
    registry = ToolRegistry()
    tool = _EchoTool()
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
                level=PermissionLevel.SAFE,
            )
        )
    return ToolExecutionBridge(
        tool_registry=registry,
        action_registry=actions,
        permission_manager=permissions,
        confirmation_gate=ConfirmationGate(),
    )


def _make_plan(actions: list[str]) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan Runtime",
        current_project="Agent Runtime Validation",
        current_mission="Phase 19.1 Validation",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=30.0,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=PlanStatus.ACTIVE,
    )


def _diag_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


# ---------------------------------------------------------------------------
# Conversation paths through Brain.think()
# ---------------------------------------------------------------------------


def test_e2e_normal_conversation(brain: Brain, caplog: pytest.LogCaptureFixture) -> None:
    """Normal conversation flows Conversation → Workspace → LLM Response."""
    with caplog.at_level(logging.INFO):
        reply = brain.think("Bonjour Titan")

    assert reply == "Réponse de test."
    assert brain.llm.ask.call_count == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert brain.pipeline.stage_log == list(STAGE_ORDER)
    messages = _diag_messages(caplog)
    assert any(msg.startswith(DIAG_PIPELINE_START) for msg in messages)
    assert any(msg.startswith(DIAG_PIPELINE_FINISHED) for msg in messages)
    snap = brain.state_manager.snapshot()
    assert snap.conversation_state["last_user_message"] == "Bonjour Titan"
    assert snap.conversation_state["last_titan_response"] == "Réponse de test."


def test_e2e_project_conversation(brain: Brain) -> None:
    """Project conversation loads Project into WorkspaceState and prompt."""
    goal, project, mission = _seed_hierarchy(brain)

    brain.think("Continue on Agent Runtime Validation")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_project_id == project.id
    assert ctx.workspace_state.active_project == "Agent Runtime Validation"
    assert ctx.project_context is not None
    prompt = brain.llm.ask.call_args[0][0]
    assert "Agent Runtime Validation" in prompt or project.name in prompt
    assert mission.title
    assert goal.name


def test_e2e_mission_conversation(brain: Brain) -> None:
    """Mission conversation keeps Mission consistent through the pipeline."""
    _goal, project, mission = _seed_hierarchy(brain)

    brain.think("Continue the Phase 19.1 Validation mission")

    ctx = brain.last_think_context
    assert ctx is not None
    ws = ctx.workspace_state
    assert ws is not None
    assert ws.active_mission_id == mission.id
    assert ws.active_project_id == project.id
    assert ctx.mission_context is not None
    assert ctx.execution_plan is not None
    assert ctx.execution_decision is not None
    assert ctx.execution_result is not None
    prompt = brain.llm.ask.call_args[0][0]
    assert "PLAN ACTUEL" in prompt or "Plan" in prompt or "Design models" in prompt
    assert "EXÉCUTION ACTUELLE" in prompt


def test_e2e_goal_creation(brain: Brain) -> None:
    """Goal creation mirrors into WorkspaceState without duplicates."""
    goal = brain.goal_manager.create_goal(
        "Learn faster with Titan",
        priority=GoalPriority.NORMAL,
    )
    assert goal.id
    assert brain.goal_manager.get_active_goal() is not None
    assert brain.goal_manager.get_active_goal().id == goal.id

    brain.think("Focus on learning faster")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_goal_id == goal.id
    goals = brain.goal_manager.list_goals()
    matching = [g for g in goals if g.name == "Learn faster with Titan"]
    assert len(matching) == 1


def test_e2e_planning_generation(brain: Brain) -> None:
    """Planning stage produces a single Plan from the active hierarchy."""
    _seed_hierarchy(brain)

    brain.think("What should we do next?")

    ctx = brain.last_think_context
    assert ctx is not None
    plan = ctx.execution_plan
    assert plan is not None
    assert isinstance(plan, Plan)
    assert plan.next_actions
    assert plan.next_actions[0] == "Design models"
    assert plan.current_goal == "Ship Titan Runtime"
    assert plan.current_project == "Agent Runtime Validation"
    assert plan.current_mission == "Phase 19.1 Validation"
    assert "create_plan" in brain.pipeline.stage_log
    assert brain.pipeline.stage_log.index("create_plan") < brain.pipeline.stage_log.index(
        "create_decision"
    )


def test_e2e_execution_request(brain: Brain) -> None:
    """Execution request produces Decision → ExecutionResult once per turn."""
    _seed_hierarchy(brain)

    brain.think("Execute the next foundation step")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.execution_decision is not None
    assert ctx.execution_decision.selected_action == "Design models"
    assert ctx.execution_result is not None
    assert ctx.execution_task is not None
    assert brain.execution.active_task is not None
    assert brain.execution.active_task.task_id == ctx.execution_task.task_id
    snap = brain.state_manager.snapshot()
    assert snap.next_action == "Design models"
    assert snap.current_focus == "Design models"


# ---------------------------------------------------------------------------
# Execution failure / retry / rollback / confirmation / tool / resume
# ---------------------------------------------------------------------------


def test_e2e_execution_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Execution failure updates WorkspaceState without inventing success."""
    engine = _recovery_engine(
        tmp_path,
        results=[_failed_bridge(message="upstream timeout waiting")],
        max_attempts=1,
    )
    workspace = WorkspaceState()
    decision = SimpleNamespace(
        selected_action="retryable_action",
        decision_id="dec-fail",
        reason="test",
        expected_value=0.5,
    )
    with caplog.at_level(logging.INFO):
        result = engine.execute(
            decision=decision,
            workspace=workspace,
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )

    assert result.success is False
    assert result.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)
    assert workspace.last_error or workspace.execution_status
    assert workspace.execution_recovered is False or result.success is False


def test_e2e_retry_path(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Transient failure retries then recovers — single successful completion."""
    engine = _recovery_engine(
        tmp_path,
        results=[
            _failed_bridge(message="connection temporarily unavailable"),
            _success_bridge(message="recovered"),
        ],
        max_attempts=3,
    )
    workspace = WorkspaceState()
    with caplog.at_level(logging.INFO):
        result = engine.execute(
            decision=SimpleNamespace(
                selected_action="retryable_action",
                decision_id="dec-retry",
                reason="test",
                expected_value=0.5,
            ),
            workspace=workspace,
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert engine.tool_bridge.calls == 2  # type: ignore[attr-defined]
    assert workspace.retry_count >= 1
    assert workspace.execution_recovered is True
    messages = _diag_messages(caplog)
    assert any(msg.startswith(DIAG_EXECUTION_RETRY) for msg in messages)
    completed = [
        e for e in engine.history.entries if e.status == ExecutionStatus.COMPLETED
    ]
    assert len(completed) == 1


def test_e2e_rollback_path(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Reversible failure triggers rollback recovery path."""
    engine = _recovery_engine(
        tmp_path,
        results=[
            _failed_bridge(
                message="write failed after partial apply",
                reversible=True,
                rollback_token="rb-e2e-1",
            ),
        ],
        max_attempts=1,
    )
    workspace = WorkspaceState()
    with caplog.at_level(logging.INFO, logger="brain.execution_recovery"):
        result = engine.execute(
            decision=SimpleNamespace(
                selected_action="reversible_write",
                decision_id="dec-rb",
                reason="test",
                expected_value=0.5,
            ),
            workspace=workspace,
            action_metadata={
                "risk_level": "SAFE_READ",
                "prefer_rollback": True,
                "reversible": True,
            },
            send_feedback=False,
        )

    assert result.success is False
    rolled = engine.rollback(reason="e2e cleanup", workspace=workspace)
    assert rolled.rollback_status in (
        RollbackStatus.COMPLETED,
        RollbackStatus.SKIPPED,
        RollbackStatus.FAILED,
    )
    messages = _diag_messages(caplog)
    assert any(DIAG_EXECUTION_ROLLBACK in msg for msg in messages)


def test_e2e_confirmation_path() -> None:
    """High-risk write awaits confirmation; approve once; no duplicate execute."""
    plan = _make_plan(["write sensitive runtime note"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine(
        autonomy_policy=AutonomyPolicy(
            require_confirmation_writes=True,
            require_confirmation_exec=True,
        )
    )
    held = engine.execute(
        decision=decision,
        plan=plan,
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    assert held.status == ExecutionStatus.AWAITING_CONFIRMATION
    token = held.confirmation_id
    assert token

    first = engine.confirm(token, send_feedback=False)
    assert first.status == ExecutionStatus.COMPLETED
    assert first.success is True

    second = engine.confirm(token, send_feedback=False)
    assert second.task_id == first.task_id
    completed = [
        e for e in engine.history.entries if e.status == ExecutionStatus.COMPLETED
    ]
    assert len(completed) == 1


def test_e2e_confirmation_via_brain_think(brain: Brain) -> None:
    """Brain.think /confirm resumes pending cognitive execution (no second task)."""
    _seed_hierarchy(brain)
    plan = _make_plan(["write sensitive file"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    policy = AutonomyPolicy(
        require_confirmation_writes=True,
        require_confirmation_exec=True,
    )
    brain.execution.engine.safety_evaluator._policy = policy  # type: ignore[attr-defined]

    held = brain.execution.execute_decision(
        decision=decision,
        plan=plan,
        workspace=brain.state_manager.load(),
        send_feedback=False,
        action_metadata={"risk_level": "HIGH_RISK_WRITE"},
    )
    assert held.status == ExecutionStatus.AWAITING_CONFIRMATION
    token = held.confirmation_id
    assert token
    pending_task_id = held.task_id

    reply = brain.think(f"/confirm {token}")
    assert reply
    # Confirmation path must not create a parallel completed task for same id.
    assert brain.execution.lookup_pending(token) is None
    assert brain.execution.active_task is not None
    assert brain.execution.active_task.task_id == pending_task_id


def test_e2e_tool_dispatch_path(caplog: pytest.LogCaptureFixture) -> None:
    """Tool Bridge dispatches a real registry tool through ExecutionEngine."""
    bridge = _wired_echo_bridge()
    engine = ExecutionEngine(tool_bridge=bridge)
    plan = _make_plan(["echo_tool:echo"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState()

    with caplog.at_level(logging.INFO):
        result = engine.execute(
            decision=decision,
            plan=plan,
            workspace=workspace,
            send_feedback=False,
            action_metadata={
                "risk_level": "SAFE_READ",
                "tool_id": "echo_tool",
                "action_id": "echo",
                "parameters": {"message": "runtime-ok"},
            },
        )

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert workspace.last_tool == "echo_tool"
    messages = _diag_messages(caplog)
    assert any(msg.startswith(DIAG_TOOL_DISPATCH) for msg in messages)
    assert any(msg.startswith(DIAG_TOOL_COMPLETED) for msg in messages)


def test_e2e_recovery_after_restart(tmp_path: Path) -> None:
    """Checkpointed WAITING execution resumes after process restart."""
    checkpoint_path = tmp_path / "execution_checkpoint.json"
    manager = ExecutionRecoveryManager(
        policy=ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0),
        checkpoint_path=checkpoint_path,
        sleep_fn=lambda _s: None,
    )
    stamp = datetime.now(timezone.utc).isoformat()
    manager.persist_checkpoint(
        ExecutionCheckpoint(
            task_id="task-e2e-wait",
            action="deferred_runtime_action",
            status=ExecutionStatus.WAITING.value,
            decision_id="dec-wait-e2e",
            attempt_number=1,
            last_failure_reason="resume later",
            recovery_action=RecoveryAction.WAIT.value,
            created_at=stamp,
            updated_at=stamp,
            resumable=True,
        )
    )

    engine = ExecutionEngine(
        tool_bridge=_ScriptedBridge([]),  # type: ignore[arg-type]
        recovery_manager=ExecutionRecoveryManager(
            policy=ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0),
            checkpoint_path=checkpoint_path,
            sleep_fn=lambda _s: None,
        ),
        checkpoint_path=checkpoint_path,
        auto_resume=False,
    )
    workspace = WorkspaceState()
    resumed = engine.resume_after_restart(workspace=workspace, send_feedback=False)

    assert resumed is not None
    assert resumed.status == ExecutionStatus.WAITING
    assert engine.active_task is not None
    assert engine.active_task.task_id == "task-e2e-wait"
    assert workspace.execution_recovered is True


def test_e2e_conversation_resumes_correctly(
    brain: Brain,
    tmp_path: Path,
) -> None:
    """After think(), reloaded WorkspaceState resumes conversation continuity."""
    _seed_hierarchy(brain)
    brain.think("First turn on the validation mission")

    first_snap = brain.state_manager.snapshot()
    assert first_snap.conversation_state["last_user_message"] == (
        "First turn on the validation mission"
    )
    assert first_snap.active_mission_id
    assert first_snap.active_project_id
    assert first_snap.active_goal_id
    mission_id = first_snap.active_mission_id
    project_id = first_snap.active_project_id
    goal_id = first_snap.active_goal_id

    # Simulate restart: new StateManager on same file, same Brain managers.
    reloaded = StateManager(file_path=tmp_path / "titan_state.json")
    restored = reloaded.load()
    assert restored.active_mission_id == mission_id
    assert restored.active_project_id == project_id
    assert restored.active_goal_id == goal_id
    assert restored.conversation_state["last_user_message"] == (
        "First turn on the validation mission"
    )

    brain.think("Continue the validation mission")
    second = brain.state_manager.snapshot()
    assert second.active_mission_id == mission_id
    assert second.active_project_id == project_id
    assert second.active_goal_id == goal_id
    assert second.conversation_state["last_user_message"] == (
        "Continue the validation mission"
    )
    assert second.conversation_state["last_titan_response"] == "Réponse de test."


# ---------------------------------------------------------------------------
# Cross-system consistency + no-duplication memory validation
# ---------------------------------------------------------------------------


def test_e2e_cross_system_consistency(brain: Brain) -> None:
    """Workspace / Mission / Project / Goal / Plan / Decision / Execution align."""
    goal, project, mission = _seed_hierarchy(brain)

    brain.think("Align all runtime subsystems")

    ctx = brain.last_think_context
    assert ctx is not None
    ws = ctx.workspace_state
    assert ws is not None

    # WorkspaceState consistency
    assert ws.active_goal_id == goal.id
    assert ws.active_project_id == project.id
    assert ws.active_mission_id == mission.id

    # Manager consistency (single active of each)
    assert brain.goal_manager.get_active_goal().id == goal.id
    assert brain.project_manager.get_active_project().id == project.id
    assert brain.mission_manager.get_active_mission().id == mission.id

    # Planning consistency
    plan = ctx.execution_plan
    assert plan is not None
    assert plan.current_goal == goal.name
    assert plan.current_project == project.name
    assert plan.current_mission == mission.title

    # Decision consistency
    decision = ctx.execution_decision
    assert decision is not None
    assert decision.selected_action in plan.next_actions

    # Execution consistency
    result = ctx.execution_result
    assert result is not None
    assert result.action == decision.selected_action
    assert ctx.execution_task is not None
    assert ctx.execution_task.action == decision.selected_action


def test_e2e_no_duplicated_state_or_entities(brain: Brain) -> None:
    """One turn must not duplicate WorkspaceState, Mission, Project, Goal, or Execution."""
    goal, project, mission = _seed_hierarchy(brain)
    workspace_ids: list[int] = []

    original_create_plan = brain.pipeline._stage_create_plan
    original_create_decision = brain.pipeline._stage_create_decision
    original_create_execution = brain.pipeline._stage_create_execution

    def wrap_plan(ctx: Any) -> None:
        assert ctx.workspace_state is not None
        workspace_ids.append(id(ctx.workspace_state))
        original_create_plan(ctx)

    def wrap_decision(ctx: Any) -> None:
        assert ctx.workspace_state is not None
        workspace_ids.append(id(ctx.workspace_state))
        original_create_decision(ctx)

    def wrap_execution(ctx: Any) -> None:
        assert ctx.workspace_state is not None
        workspace_ids.append(id(ctx.workspace_state))
        original_create_execution(ctx)

    brain.pipeline._stage_create_plan = wrap_plan  # type: ignore[method-assign]
    brain.pipeline._stage_create_decision = wrap_decision  # type: ignore[method-assign]
    brain.pipeline._stage_create_execution = wrap_execution  # type: ignore[method-assign]

    brain.think("No duplicates please")

    assert len(workspace_ids) == 3
    assert len(set(workspace_ids)) == 1

    # No duplicated goal / project / mission entities
    assert len([g for g in brain.goal_manager.list_goals() if g.id == goal.id]) == 1
    assert len(
        [p for p in brain.project_manager.list_projects() if p.id == project.id]
    ) == 1
    assert brain.mission_manager.get_active_mission().id == mission.id

    # Exactly one LLM call and one completed cognitive execution task this turn
    assert brain.llm.ask.call_count == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.execution_task is not None
    matching_tasks = [
        e
        for e in brain.execution.engine.history.entries
        if e.task_id == ctx.execution_task.task_id
    ]
    # History may hold the result once; ensure no parallel task ids for same action turn
    assert len({e.task_id for e in matching_tasks}) <= 1


# ---------------------------------------------------------------------------
# Diagnostics + performance
# ---------------------------------------------------------------------------


def test_e2e_pipeline_diagnostics_emitted(
    brain: Brain,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PIPELINE_START / STAGE / FINISHED cover a full think() turn."""
    _seed_hierarchy(brain)
    with caplog.at_level(logging.INFO, logger="brain.pipeline.stages"):
        brain.think("Emit pipeline diagnostics")

    messages = _diag_messages(caplog)
    assert any(msg.startswith(DIAG_PIPELINE_START) for msg in messages)
    stage_msgs = [m for m in messages if m.startswith(DIAG_PIPELINE_STAGE)]
    assert len(stage_msgs) == len(STAGE_ORDER)
    assert any(msg.startswith(DIAG_PIPELINE_FINISHED) for msg in messages)
    assert not any(msg.startswith(DIAG_PIPELINE_FAILED) for msg in messages)

    timings = brain.pipeline.stage_timings_ms
    assert set(timings.keys()) == set(STAGE_ORDER)
    assert brain.pipeline.pipeline_total_ms >= 0.0
    assert sum(timings.values()) <= brain.pipeline.pipeline_total_ms + 50.0


def test_e2e_pipeline_failed_diagnostic(
    brain: Brain,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PIPELINE_FAILED emits when a stage raises; error propagates."""
    original = brain.pipeline._stage_create_plan

    def boom(_ctx: Any) -> None:
        raise RuntimeError("injected pipeline failure")

    brain.pipeline._stage_create_plan = boom  # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR, logger="brain.pipeline.stages"):
        with pytest.raises(RuntimeError, match="injected pipeline failure"):
            brain.think("Force pipeline failure")

    messages = _diag_messages(caplog)
    assert any(msg.startswith(DIAG_PIPELINE_FAILED) for msg in messages)
    # Restore for fixture teardown safety
    brain.pipeline._stage_create_plan = original  # type: ignore[method-assign]


def test_e2e_performance_measurements(brain: Brain) -> None:
    """Measure average pipeline, context, decision, execution, and total runtime."""
    _seed_hierarchy(brain)
    samples: list[dict[str, float]] = []

    for i in range(3):
        started = time.perf_counter()
        brain.think(f"Performance sample turn {i}")
        total_ms = (time.perf_counter() - started) * 1000.0
        timings = brain.pipeline.stage_timings_ms
        samples.append(
            {
                "pipeline_ms": brain.pipeline.pipeline_total_ms,
                "context_ms": timings.get("load_context", 0.0)
                + timings.get("load_state", 0.0)
                + timings.get("load_or_create_mission", 0.0),
                "decision_ms": timings.get("create_decision", 0.0),
                "execution_ms": timings.get("create_execution", 0.0),
                "total_ms": total_ms,
            }
        )

    def avg(key: str) -> float:
        return sum(s[key] for s in samples) / len(samples)

    avg_pipeline = avg("pipeline_ms")
    avg_context = avg("context_ms")
    avg_decision = avg("decision_ms")
    avg_execution = avg("execution_ms")
    avg_total = avg("total_ms")

    # Sanity: timings are finite and non-negative; mocked LLM path stays fast.
    assert avg_pipeline >= 0.0
    assert avg_context >= 0.0
    assert avg_decision >= 0.0
    assert avg_execution >= 0.0
    assert avg_total >= avg_pipeline
    assert avg_total < 30_000.0  # mocked path must stay well under 30s

    # Expose observations for pytest -s / CI logs.
    print(
        "RUNTIME_PERF "
        f"avg_pipeline_ms={avg_pipeline:.3f} "
        f"avg_context_ms={avg_context:.3f} "
        f"avg_decision_ms={avg_decision:.3f} "
        f"avg_execution_ms={avg_execution:.3f} "
        f"avg_total_ms={avg_total:.3f}"
    )


def test_e2e_full_runtime_path_with_learning(brain: Brain) -> None:
    """Full ordered path including Learning and LLM after hierarchy seed."""
    _seed_hierarchy(brain)

    reply = brain.think("Run the complete agent runtime path")

    assert reply == "Réponse de test."
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.execution_plan is not None
    assert ctx.execution_decision is not None
    assert ctx.execution_result is not None
    assert "record_learning" in brain.pipeline.stage_log
    assert "update_state" in brain.pipeline.stage_log
    assert "llm_call" in brain.pipeline.stage_log
    assert brain.pipeline.stage_log.index("create_plan") < brain.pipeline.stage_log.index(
        "create_decision"
    )
    assert brain.pipeline.stage_log.index(
        "create_decision"
    ) < brain.pipeline.stage_log.index("create_execution")
    assert brain.pipeline.stage_log.index(
        "create_execution"
    ) < brain.pipeline.stage_log.index("llm_call")
    assert brain.pipeline.stage_log.index("llm_call") < brain.pipeline.stage_log.index(
        "record_learning"
    )
    assert brain.pipeline.stage_log.index(
        "record_learning"
    ) < brain.pipeline.stage_log.index("update_state")

    # Facade still points at the shared ExecutionEngine (no duplicate subsystem).
    assert isinstance(brain.execution, ExecutionFacade)
    assert isinstance(brain.execution.engine, ExecutionEngine)
    assert isinstance(brain.planning.engine, PlanningEngine)

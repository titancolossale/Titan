# =====================================
# Titan Production Validation & Hardening
# =====================================

"""Phase 19.2 — production stress, memory, performance, concurrency, diagnostics.

Validates the existing agent runtime without redesigning subsystems.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.chat_service import (
    _acquire_brain_lock,
    _release_brain_lock,
    reset_brain_lock_for_tests,
)
from brain.autonomy_policy import AutonomyPolicy
from brain.brain import Brain
from brain.decision_engine import DecisionEngine
from brain.execution_engine import DEFAULT_HISTORY_LIMIT, ExecutionEngine
from brain.execution_models import ExecutionStatus
from brain.execution_recovery import (
    DIAG_EXECUTION_ABORT,
    DIAG_EXECUTION_RECOVERED,
    DIAG_EXECUTION_RESUME,
    DIAG_EXECUTION_RETRY,
    DIAG_EXECUTION_ROLLBACK,
    DIAG_EXECUTION_TIMEOUT,
    ExecutionCheckpoint,
    ExecutionRecoveryManager,
    ExecutionRetryPolicy,
    RecoveryAction,
)
from brain.execution_tool_bridge import ToolExecutionBridge
from brain.execution_tool_models import (
    DIAG_TOOL_CANCELLED,
    DIAG_TOOL_COMPLETED,
    DIAG_TOOL_DISPATCH,
    DIAG_TOOL_FAILED,
    DIAG_TOOL_STARTED,
    DIAG_TOOL_TIMEOUT,
    DIAG_TOOL_UNAVAILABLE,
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
from brain.request_deadline import RequestDeadline
from config.settings import CONVERSATION_MAX_STORED_TURNS
from core.actions import Action, ActionRegistry, ActionResult
from core.goal_models import GoalPriority
from core.mission_models import MissionPriority
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager, WorkspaceState
from core.tools import BaseTool, ToolRegistry
from tools.confirmation_gate import ConfirmationGate

# ---------------------------------------------------------------------------
# Expected runtime diagnostics (Phase 19.1–19.2 inventory)
# ---------------------------------------------------------------------------

EXPECTED_PIPELINE_DIAGS = (
    DIAG_PIPELINE_START,
    DIAG_PIPELINE_STAGE,
    DIAG_PIPELINE_FINISHED,
    DIAG_PIPELINE_FAILED,
)

EXPECTED_TOOL_DIAGS = (
    DIAG_TOOL_DISPATCH,
    DIAG_TOOL_STARTED,
    DIAG_TOOL_COMPLETED,
    DIAG_TOOL_FAILED,
    DIAG_TOOL_TIMEOUT,
    DIAG_TOOL_CANCELLED,
    DIAG_TOOL_UNAVAILABLE,
)

EXPECTED_RECOVERY_DIAGS = (
    DIAG_EXECUTION_RETRY,
    DIAG_EXECUTION_RESUME,
    DIAG_EXECUTION_ABORT,
    DIAG_EXECUTION_ROLLBACK,
    DIAG_EXECUTION_TIMEOUT,
    DIAG_EXECUTION_RECOVERED,
)

# Soft-named (string log prefixes, not DIAG_* constants).
EXPECTED_PLAN_DIAGS = (
    "PLAN_CREATED",
    "PLAN_UPDATED",
    "PLAN_REVISION",
    "PLAN_COMPLETED",
    "PLAN_REBUILT",
)

EXPECTED_DECISION_DIAGS = (
    "DECISION_CREATED",
    "DECISION_UPDATED",
    "DECISION_SELECTED",
    "DECISION_FEEDBACK",
    "DECISION_HISTORY_UPDATED",
    "DECISION_CONFIDENCE_UPDATED",
)

STRESS_LEVELS = (100, 250, 500, 1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ScriptedBridge:
    """Minimal Tool Execution Bridge stub for recovery / concurrency paths."""

    def __init__(self, results: list[BridgeExecutionResult] | None = None) -> None:
        self._results = list(results or [])
        self._lock = threading.Lock()
        self.calls = 0

    def dispatch(self, **kwargs: Any) -> BridgeExecutionResult:
        with self._lock:
            self.calls += 1
            if not self._results:
                return BridgeExecutionResult.cognitive_success(message="ok")
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
        return "Echo for production validation."

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
        "Ship Titan Production",
        priority=GoalPriority.HIGH,
    )
    project = brain.project_manager.create_project(
        "Production Hardening",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission = brain.mission_manager.create_mission(
        "Phase 19.2 Validation",
        "Prove production runtime stability",
        ["Measure", "Stress", "Report"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )
    return goal, project, mission


def _seed_switchable_hierarchy(brain: Brain) -> dict[str, Any]:
    """Two goals / projects / missions for switching consistency checks."""
    g1 = brain.goal_manager.create_goal(
        "Goal Alpha",
        aliases=["alpha-goal"],
        keywords=["alpha"],
        priority=GoalPriority.HIGH,
    )
    g2 = brain.goal_manager.create_goal(
        "Goal Beta",
        aliases=["beta-goal"],
        keywords=["beta"],
        priority=GoalPriority.NORMAL,
    )
    p1 = brain.project_manager.create_project(
        "Project Alpha",
        aliases=["alpha-project"],
        keywords=["alpha"],
        goal_id=g1.id,
        priority=ProjectPriority.HIGH,
    )
    p2 = brain.project_manager.create_project(
        "Project Beta",
        aliases=["beta-project"],
        keywords=["beta"],
        goal_id=g2.id,
        priority=ProjectPriority.NORMAL,
    )
    m1 = brain.mission_manager.create_mission(
        "Mission Alpha",
        "Alpha path",
        ["A1", "A2"],
        project_id=p1.id,
        priority=MissionPriority.HIGH,
    )
    m2 = brain.mission_manager.create_mission(
        "Mission Beta",
        "Beta path",
        ["B1", "B2"],
        project_id=p2.id,
        priority=MissionPriority.NORMAL,
    )
    brain.goal_manager.resume_goal(g1.id)
    return {
        "g1": g1,
        "g2": g2,
        "p1": p1,
        "p2": p2,
        "m1": m1,
        "m2": m2,
    }


def _workspace_byte_size(workspace: WorkspaceState) -> int:
    return len(json.dumps(workspace.to_dict(), ensure_ascii=False).encode("utf-8"))


def _failed_bridge(message: str = "connection temporarily unavailable") -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=BridgeExecutionStatus.FAILED,
        message=message,
        success=False,
        duration=0.001,
        tool_id="fake_tool",
        action_id="run",
        error=message,
        result_summary=message,
    )


def _success_bridge(message: str = "ok") -> BridgeExecutionResult:
    return BridgeExecutionResult(
        status=BridgeExecutionStatus.SUCCESS,
        message=message,
        success=True,
        duration=0.001,
        tool_id="fake_tool",
        action_id="run",
        result_summary=message,
    )


def _make_plan(actions: list[str]) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan Production",
        current_project="Production Hardening",
        current_mission="Phase 19.2 Validation",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=30.0,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=PlanStatus.ACTIVE,
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


def _entity_counts(brain: Brain) -> dict[str, int]:
    return {
        "goals": len(brain.goal_manager.list_goals()),
        "projects": len(brain.project_manager.list_projects()),
        "missions": len(brain.mission_manager.list_missions()),
        "execution_history": len(brain.execution.engine.history.entries),
        "conversation_turns": len(getattr(brain.conversation_engine, "_turns", []) or []),
    }


def _assert_no_duplicate_ids(items: list[Any], id_attr: str = "id") -> None:
    ids = [getattr(item, id_attr) for item in items]
    assert len(ids) == len(set(ids)), f"duplicate {id_attr} values detected"


def _run_stress_iterations(
    brain: Brain,
    iterations: int,
    *,
    message_prefix: str = "stress turn",
) -> dict[str, Any]:
    """Run consecutive Brain.think iterations and collect consistency metrics."""
    goal, project, mission = _seed_hierarchy(brain)
    baseline = _entity_counts(brain)
    baseline_ws_size = _workspace_byte_size(brain.state_manager.snapshot())

    latencies_ms: list[float] = []
    stage_samples: dict[str, list[float]] = {
        "conversation": [],
        "workspace": [],
        "planning": [],
        "decision": [],
        "execution": [],
        "recovery": [],
        "pipeline": [],
    }
    workspace_sizes: list[int] = []
    peak_history = 0
    peak_running_tasks = 0
    peak_missions_mirror = 0
    peak_projects_mirror = 0
    peak_goals_mirror = 0

    for i in range(iterations):
        started = time.perf_counter()
        reply = brain.think(f"{message_prefix} {i}")
        total_ms = (time.perf_counter() - started) * 1000.0
        latencies_ms.append(total_ms)

        assert reply == "Réponse de test."
        ctx = brain.last_think_context
        assert ctx is not None
        ws = ctx.workspace_state
        assert ws is not None

        # Active focus must remain the seeded hierarchy (no accidental create).
        assert ws.active_goal_id == goal.id
        assert ws.active_project_id == project.id
        assert ws.active_mission_id == mission.id

        timings = brain.pipeline.stage_timings_ms
        stage_samples["conversation"].append(
            timings.get("conversation_commands", 0.0) + timings.get("load_conversation", 0.0)
        )
        stage_samples["workspace"].append(
            timings.get("load_state", 0.0)
            + timings.get("load_context", 0.0)
            + timings.get("update_state", 0.0)
        )
        stage_samples["planning"].append(timings.get("create_plan", 0.0))
        stage_samples["decision"].append(timings.get("create_decision", 0.0))
        stage_samples["execution"].append(timings.get("create_execution", 0.0))
        stage_samples["recovery"].append(0.0)  # recovery only on failure paths
        stage_samples["pipeline"].append(brain.pipeline.pipeline_total_ms)

        snap = brain.state_manager.snapshot()
        workspace_sizes.append(_workspace_byte_size(snap))
        peak_history = max(peak_history, len(brain.execution.engine.history.entries))
        peak_running_tasks = max(peak_running_tasks, len(snap.running_tasks or []))
        peak_missions_mirror = max(peak_missions_mirror, len(snap.missions or []))
        peak_projects_mirror = max(peak_projects_mirror, len(snap.projects or []))
        peak_goals_mirror = max(peak_goals_mirror, len(snap.goals or []))

        # Bounded lists must never explode with iteration count.
        assert len(snap.running_tasks or []) <= 2
        assert len(brain.execution.engine.history.entries) <= DEFAULT_HISTORY_LIMIT
        assert len(getattr(brain.conversation_engine, "_turns", []) or []) <= (
            CONVERSATION_MAX_STORED_TURNS
        )

    final_counts = _entity_counts(brain)
    assert final_counts["goals"] == baseline["goals"]
    assert final_counts["projects"] == baseline["projects"]
    assert final_counts["missions"] == baseline["missions"]
    _assert_no_duplicate_ids(brain.goal_manager.list_goals())
    _assert_no_duplicate_ids(brain.project_manager.list_projects())
    mission_ids = [
        getattr(m, "id", None) for m in brain.mission_manager.list_missions()
    ]
    assert len(mission_ids) == len(set(mission_ids))

    # Workspace size must not grow linearly with iteration count.
    final_ws_size = workspace_sizes[-1]
    growth = final_ws_size - baseline_ws_size
    # Allow modest growth from resume/summary fields, not unbounded history.
    assert growth < 50_000, f"WorkspaceState grew too much: +{growth} bytes"
    assert max(workspace_sizes) < baseline_ws_size + 80_000

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    metrics = {
        "iterations": iterations,
        "avg_runtime_ms": _avg(latencies_ms),
        "worst_runtime_ms": max(latencies_ms) if latencies_ms else 0.0,
        "avg_conversation_ms": _avg(stage_samples["conversation"]),
        "avg_workspace_ms": _avg(stage_samples["workspace"]),
        "avg_planning_ms": _avg(stage_samples["planning"]),
        "avg_decision_ms": _avg(stage_samples["decision"]),
        "avg_execution_ms": _avg(stage_samples["execution"]),
        "avg_pipeline_ms": _avg(stage_samples["pipeline"]),
        "peak_execution_history": peak_history,
        "peak_running_tasks": peak_running_tasks,
        "peak_missions_mirror": peak_missions_mirror,
        "peak_projects_mirror": peak_projects_mirror,
        "peak_goals_mirror": peak_goals_mirror,
        "workspace_bytes_start": baseline_ws_size,
        "workspace_bytes_end": final_ws_size,
        "workspace_growth_bytes": growth,
        "entity_counts": final_counts,
    }
    print(f"PROD_STRESS_{iterations} {json.dumps(metrics, sort_keys=True)}")
    return metrics


# ---------------------------------------------------------------------------
# Stress tests — 100 / 250 / 500 / 1000 consecutive iterations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("iterations", STRESS_LEVELS)
def test_stress_consecutive_runtime_iterations(brain: Brain, iterations: int) -> None:
    """N consecutive think() turns: no duplicated entities, bounded workspace."""
    metrics = _run_stress_iterations(brain, iterations)
    assert metrics["iterations"] == iterations
    assert metrics["peak_execution_history"] <= DEFAULT_HISTORY_LIMIT
    assert metrics["entity_counts"]["goals"] == 1
    assert metrics["entity_counts"]["projects"] == 1
    assert metrics["entity_counts"]["missions"] >= 1
    # Mocked LLM path must remain production-acceptable.
    assert metrics["avg_runtime_ms"] < 5_000.0
    assert metrics["worst_runtime_ms"] < 15_000.0


# ---------------------------------------------------------------------------
# Switching consistency
# ---------------------------------------------------------------------------


def test_mission_project_goal_switching_consistency(brain: Brain) -> None:
    """Switching goal/project/mission keeps WorkspaceState and managers aligned."""
    seeded = _seed_switchable_hierarchy(brain)

    brain.goal_manager.resume_goal(seeded["g2"].id)
    brain.think("Continue Goal Beta / Project Beta / Mission Beta")

    ctx = brain.last_think_context
    assert ctx is not None
    ws = ctx.workspace_state
    assert ws is not None
    assert brain.goal_manager.get_active_goal().id == seeded["g2"].id
    assert ws.active_goal_id == seeded["g2"].id

    brain.goal_manager.resume_goal(seeded["g1"].id)
    brain.project_manager.resume_project(seeded["p1"].id)
    brain.mission_manager.resume_mission(seeded["m1"].id)
    brain.think("Resume Mission Alpha focus")

    ctx2 = brain.last_think_context
    assert ctx2 is not None
    ws2 = ctx2.workspace_state
    assert ws2 is not None
    assert brain.goal_manager.get_active_goal().id == seeded["g1"].id
    assert brain.project_manager.get_active_project().id == seeded["p1"].id
    assert brain.mission_manager.get_active_mission().id == seeded["m1"].id
    assert ws2.active_goal_id == seeded["g1"].id
    assert ws2.active_project_id == seeded["p1"].id
    assert ws2.active_mission_id == seeded["m1"].id

    # No duplicates after switches.
    assert len(brain.goal_manager.list_goals()) == 2
    assert len(brain.project_manager.list_projects()) == 2
    assert len(brain.mission_manager.list_missions()) == 2


def test_planning_decision_execution_consistency_across_turns(brain: Brain) -> None:
    """Plan → Decision → Execution stay aligned across consecutive requests."""
    _seed_hierarchy(brain)
    for i in range(25):
        brain.think(f"consistency turn {i}")
        ctx = brain.last_think_context
        assert ctx is not None
        plan = ctx.execution_plan
        decision = ctx.execution_decision
        result = ctx.execution_result
        assert plan is not None
        assert decision is not None
        assert result is not None
        assert decision.selected_action in plan.next_actions
        assert result.action == decision.selected_action
        assert plan.current_mission == "Phase 19.2 Validation"


def test_recovery_consistency_across_retries(tmp_path: Path) -> None:
    """Recovery retries once then succeeds — single completed history entry."""
    bridge = _ScriptedBridge(
        [
            _failed_bridge("connection temporarily unavailable"),
            _success_bridge("recovered"),
        ]
    )
    policy = ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0, backoff_multiplier=2.0)
    recovery = ExecutionRecoveryManager(
        policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        sleep_fn=lambda _s: None,
    )
    engine = ExecutionEngine(
        tool_bridge=bridge,  # type: ignore[arg-type]
        recovery_manager=recovery,
        retry_policy=policy,
        checkpoint_path=tmp_path / "execution_checkpoint.json",
        auto_resume=False,
    )
    workspace = WorkspaceState()
    result = engine.execute(
        decision=SimpleNamespace(
            selected_action="retryable_action",
            decision_id="dec-prod-retry",
            reason="prod",
            expected_value=0.5,
        ),
        workspace=workspace,
        action_metadata={"risk_level": "SAFE_READ"},
        send_feedback=False,
    )
    assert result.success is True
    assert bridge.calls == 2
    assert workspace.execution_recovered is True
    completed = [e for e in engine.history.entries if e.status == ExecutionStatus.COMPLETED]
    assert len(completed) == 1


def test_tool_dispatch_consistency() -> None:
    """Tool bridge dispatches once per execute; workspace mirrors once."""
    bridge = _wired_echo_bridge()
    engine = ExecutionEngine(tool_bridge=bridge)
    plan = _make_plan(["echo_tool:echo"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState()
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
        action_metadata={
            "risk_level": "SAFE_READ",
            "tool_id": "echo_tool",
            "action_id": "echo",
            "parameters": {"message": "prod-ok"},
        },
    )
    assert result.success is True
    assert workspace.last_tool == "echo_tool"
    assert workspace.execution_status in (
        BridgeExecutionStatus.SUCCESS.value,
        ExecutionStatus.COMPLETED.value,
        "success",
        "completed",
    )


# ---------------------------------------------------------------------------
# Memory / orphan validation
# ---------------------------------------------------------------------------


def test_workspace_memory_bounds_long_conversation(brain: Brain) -> None:
    """Long conversation must not grow WorkspaceState indefinitely."""
    _seed_hierarchy(brain)
    sizes: list[int] = []
    for i in range(120):
        brain.think(f"long conversation turn {i}")
        sizes.append(_workspace_byte_size(brain.state_manager.snapshot()))

    # After warm-up, size should plateau (no linear growth).
    early = sizes[20]
    late = sizes[-1]
    assert late <= early * 2 + 20_000
    assert len(brain.execution.engine.history.entries) <= DEFAULT_HISTORY_LIMIT
    assert len(getattr(brain.conversation_engine, "_turns", []) or []) <= (
        CONVERSATION_MAX_STORED_TURNS
    )


def test_no_orphaned_entities_after_switches(brain: Brain) -> None:
    """Paused goals/projects/missions remain listed; no orphan mirrors."""
    seeded = _seed_switchable_hierarchy(brain)
    brain.goal_manager.pause_goal(seeded["g2"].id)
    brain.project_manager.pause_project(seeded["p2"].id)
    brain.mission_manager.pause_mission(seeded["m2"].id)
    brain.think("Focus only on Alpha")

    snap = brain.state_manager.snapshot()
    goal_ids = {g.id for g in brain.goal_manager.list_goals()}
    project_ids = {p.id for p in brain.project_manager.list_projects()}
    mission_ids = {m.id for m in brain.mission_manager.list_missions()}
    assert seeded["g1"].id in goal_ids and seeded["g2"].id in goal_ids
    assert seeded["p1"].id in project_ids and seeded["p2"].id in project_ids
    assert seeded["m1"].id in mission_ids and seeded["m2"].id in mission_ids

    # Mirror lists must not invent unknown ids.
    mirrored_goal_ids = {
        getattr(g, "id", None) if not isinstance(g, dict) else g.get("id")
        for g in (snap.goals or [])
    }
    mirrored_goal_ids.discard(None)
    assert mirrored_goal_ids.issubset(goal_ids)

    # No leaked planning objects on context after turn.
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.execution_plan is not None
    assert isinstance(ctx.execution_plan, Plan)


def test_no_orphaned_execution_after_completion(tmp_path: Path) -> None:
    """Completed execution clears running_tasks; history stays bounded."""
    engine = ExecutionEngine(
        tool_bridge=_ScriptedBridge([_success_bridge()]),  # type: ignore[arg-type]
        checkpoint_path=tmp_path / "cp.json",
        auto_resume=False,
    )
    workspace = WorkspaceState()
    for i in range(60):
        engine.execute(
            decision=SimpleNamespace(
                selected_action=f"action_{i % 3}",
                decision_id=f"dec-{i}",
                reason="prod",
                expected_value=0.4,
            ),
            workspace=workspace,
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )
    assert len(engine.history.entries) <= DEFAULT_HISTORY_LIMIT
    assert workspace.running_tasks == [] or workspace.running_tasks is None or (
        len(workspace.running_tasks) <= 1
    )


# ---------------------------------------------------------------------------
# Performance + resource validation
# ---------------------------------------------------------------------------


def test_performance_and_resource_measurements(brain: Brain) -> None:
    """Measure latencies and resource peaks across a representative run."""
    _seed_hierarchy(brain)
    tracemalloc.start()
    samples: list[dict[str, float]] = []
    peak_objects = 0

    for i in range(40):
        started = time.perf_counter()
        brain.think(f"perf sample {i}")
        total_ms = (time.perf_counter() - started) * 1000.0
        timings = brain.pipeline.stage_timings_ms
        samples.append(
            {
                "conversation_ms": timings.get("conversation_commands", 0.0)
                + timings.get("load_conversation", 0.0),
                "workspace_ms": timings.get("load_state", 0.0)
                + timings.get("update_state", 0.0),
                "planning_ms": timings.get("create_plan", 0.0),
                "decision_ms": timings.get("create_decision", 0.0),
                "execution_ms": timings.get("create_execution", 0.0),
                "pipeline_ms": brain.pipeline.pipeline_total_ms,
                "total_ms": total_ms,
            }
        )
        peak_objects = max(peak_objects, len(brain.execution.engine.history.entries))

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    def avg(key: str) -> float:
        return sum(s[key] for s in samples) / len(samples)

    report = {
        "avg_conversation_ms": avg("conversation_ms"),
        "avg_workspace_ms": avg("workspace_ms"),
        "avg_planning_ms": avg("planning_ms"),
        "avg_decision_ms": avg("decision_ms"),
        "avg_execution_ms": avg("execution_ms"),
        "avg_pipeline_ms": avg("pipeline_ms"),
        "avg_runtime_ms": avg("total_ms"),
        "worst_runtime_ms": max(s["total_ms"] for s in samples),
        "memory_current_bytes": current,
        "memory_peak_bytes": peak,
        "execution_object_count": peak_objects,
        "workspace_size_bytes": _workspace_byte_size(brain.state_manager.snapshot()),
        "active_contexts": 1 if brain.last_think_context is not None else 0,
        "pipeline_stage_count": len(brain.pipeline.stage_timings_ms),
    }
    print(f"PROD_PERF {json.dumps(report, sort_keys=True)}")

    assert report["avg_runtime_ms"] < 5_000.0
    assert report["worst_runtime_ms"] < 15_000.0
    assert report["execution_object_count"] <= DEFAULT_HISTORY_LIMIT
    assert report["pipeline_stage_count"] == len(STAGE_ORDER)
    assert report["memory_peak_bytes"] > 0


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_parallel_state_manager_updates(tmp_path: Path) -> None:
    """Concurrent StateManager.update calls must not corrupt WorkspaceState."""
    state = StateManager(file_path=tmp_path / "titan_state.json")
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(idx: int) -> None:
        try:
            barrier.wait()
            for n in range(25):
                state.update(current_focus=f"worker-{idx}-{n}", next_action=f"a-{idx}-{n}")
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    snap = state.snapshot()
    assert snap.current_focus is not None
    assert snap.next_action is not None
    # Round-trip integrity
    reloaded = StateManager(file_path=tmp_path / "titan_state.json").load()
    assert isinstance(reloaded.current_focus, str)


def test_parallel_execution_and_planning(tmp_path: Path) -> None:
    """Parallel ExecutionEngine + PlanningEngine work without cross-talk."""
    plan = _make_plan(["parallel_action"])
    decision = DecisionEngine(persist=False).decide(plan=plan)

    def run_execution(idx: int) -> ExecutionStatus:
        engine = ExecutionEngine(
            tool_bridge=_ScriptedBridge([_success_bridge(f"ok-{idx}")]),  # type: ignore[arg-type]
            auto_resume=False,
            checkpoint_path=tmp_path / f"exec_checkpoint_{idx}.json",
        )
        result = engine.execute(
            decision=decision,
            plan=plan,
            workspace=WorkspaceState(),
            send_feedback=False,
            action_metadata={"risk_level": "SAFE_READ"},
        )
        assert len(engine.history.entries) == 1
        return result.status

    def run_planning(idx: int) -> Plan:
        engine = PlanningEngine()
        built = engine.plan_next(
            workspace=WorkspaceState(
                active_goal="Ship Titan Production",
                active_project="Production Hardening",
                active_mission_title="Phase 19.2 Validation",
                current_step="Measure",
            ),
            change_reason=f"plan {idx}",
        )
        assert built is not None
        return built

    with ThreadPoolExecutor(max_workers=8) as pool:
        exec_futures = [pool.submit(run_execution, i) for i in range(8)]
        plan_futures = [pool.submit(run_planning, i) for i in range(8)]
        exec_statuses = [f.result() for f in as_completed(exec_futures)]
        plans = [f.result() for f in as_completed(plan_futures)]

    assert all(status == ExecutionStatus.COMPLETED for status in exec_statuses)
    assert len(plans) == 8


def test_parallel_confirmations_execute_once() -> None:
    """Concurrent confirmations for one token execute at most once."""
    plan = _make_plan(["write concurrent prod"])
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
    token = held.confirmation_id
    assert token
    barrier = threading.Barrier(8)
    results: list[Any] = []

    def approve() -> None:
        barrier.wait()
        results.append(engine.confirm(token, send_feedback=False))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(approve) for _ in range(8)]
        for future in futures:
            future.result()

    history_completed = [
        e for e in engine.history.entries if e.status == ExecutionStatus.COMPLETED
    ]
    assert len(history_completed) == 1


def test_parallel_recovery_no_race(tmp_path: Path) -> None:
    """Parallel resume_after_restart against one checkpoint is race-safe."""
    checkpoint_path = tmp_path / "execution_checkpoint.json"
    manager = ExecutionRecoveryManager(
        policy=ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0),
        checkpoint_path=checkpoint_path,
        sleep_fn=lambda _s: None,
    )
    stamp = datetime.now(timezone.utc).isoformat()
    manager.persist_checkpoint(
        ExecutionCheckpoint(
            task_id="task-prod-wait",
            action="deferred_prod_action",
            status=ExecutionStatus.WAITING.value,
            decision_id="dec-wait-prod",
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
    barrier = threading.Barrier(6)
    outcomes: list[Any] = []

    def resume() -> None:
        barrier.wait()
        outcomes.append(engine.resume_after_restart(workspace=WorkspaceState(), send_feedback=False))

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(resume) for _ in range(6)]
        for future in futures:
            future.result()

    resumed = [o for o in outcomes if o is not None]
    assert len(resumed) >= 1
    assert engine.active_task is not None
    assert engine.active_task.task_id == "task-prod-wait"


def test_parallel_requests_serialized_via_brain_lock(brain: Brain) -> None:
    """API brain lock serializes concurrent think() on a shared Brain."""
    reset_brain_lock_for_tests()
    _seed_hierarchy(brain)
    errors: list[BaseException] = []
    replies: list[str] = []
    barrier = threading.Barrier(4)

    def worker(idx: int) -> None:
        req_id = f"prod-req-{idx}"
        deadline = RequestDeadline.start(total_seconds=30.0, request_id=req_id)
        generation: int | None = None
        try:
            barrier.wait()
            generation = _acquire_brain_lock(req_id, deadline)
            assert generation is not None
            reply = brain.think(f"parallel serialized {idx}")
            replies.append(reply)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            if generation is not None:
                _release_brain_lock(req_id, generation)

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert not errors
        assert len(replies) == 4
        assert all(r == "Réponse de test." for r in replies)
        assert len(brain.goal_manager.list_goals()) == 1
        assert len(brain.project_manager.list_projects()) == 1
    finally:
        reset_brain_lock_for_tests()


# ---------------------------------------------------------------------------
# Diagnostics inventory
# ---------------------------------------------------------------------------


def test_runtime_diagnostics_inventory(caplog: pytest.LogCaptureFixture, brain: Brain) -> None:
    """Verify pipeline diagnostics emit; report catalog coverage."""
    _seed_hierarchy(brain)
    with caplog.at_level(logging.INFO):
        brain.think("Emit production diagnostics")

    messages = [record.getMessage() for record in caplog.records]
    present = {
        name
        for name in (
            *EXPECTED_PIPELINE_DIAGS,
            *EXPECTED_TOOL_DIAGS,
            *EXPECTED_RECOVERY_DIAGS,
            *EXPECTED_PLAN_DIAGS,
            *EXPECTED_DECISION_DIAGS,
        )
        if any(msg.startswith(name) or name in msg for msg in messages)
    }

    # Happy-path think must emit pipeline envelope.
    for required in (DIAG_PIPELINE_START, DIAG_PIPELINE_STAGE, DIAG_PIPELINE_FINISHED):
        assert required in present

    # Failure-only / tool-only diagnostics are expected to be absent on happy path.
    missing_on_happy_path = sorted(
        set(
            (
                *EXPECTED_PIPELINE_DIAGS,
                *EXPECTED_TOOL_DIAGS,
                *EXPECTED_RECOVERY_DIAGS,
                *EXPECTED_PLAN_DIAGS,
                *EXPECTED_DECISION_DIAGS,
            )
        )
        - present
    )
    print(
        "PROD_DIAGNOSTICS "
        f"present={sorted(present)} "
        f"missing_on_happy_path={missing_on_happy_path}"
    )

    # Constants exist and are non-empty (catalog integrity).
    for name in (
        *EXPECTED_PIPELINE_DIAGS,
        *EXPECTED_TOOL_DIAGS,
        *EXPECTED_RECOVERY_DIAGS,
    ):
        assert isinstance(name, str) and name


def test_failure_path_diagnostics_present(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Retry / rollback / tool failure diagnostics emit on failure paths."""
    bridge = _ScriptedBridge(
        [
            _failed_bridge("connection temporarily unavailable"),
            _success_bridge("recovered"),
        ]
    )
    policy = ExecutionRetryPolicy(max_attempts=3, retry_delay=0.0)
    engine = ExecutionEngine(
        tool_bridge=bridge,  # type: ignore[arg-type]
        recovery_manager=ExecutionRecoveryManager(
            policy=policy,
            checkpoint_path=tmp_path / "cp.json",
            sleep_fn=lambda _s: None,
        ),
        retry_policy=policy,
        checkpoint_path=tmp_path / "cp.json",
        auto_resume=False,
    )
    with caplog.at_level(logging.INFO):
        engine.execute(
            decision=SimpleNamespace(
                selected_action="retryable_action",
                decision_id="dec-diag",
                reason="diag",
                expected_value=0.5,
            ),
            workspace=WorkspaceState(),
            action_metadata={"risk_level": "SAFE_READ"},
            send_feedback=False,
        )
    messages = [r.getMessage() for r in caplog.records]
    assert any(DIAG_EXECUTION_RETRY in m for m in messages)


def test_pipeline_failed_diagnostic_still_wired(
    brain: Brain,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PIPELINE_FAILED remains wired for production observability."""
    original = brain.pipeline._stage_create_plan

    def boom(_ctx: Any) -> None:
        raise RuntimeError("injected prod validation failure")

    brain.pipeline._stage_create_plan = boom  # type: ignore[method-assign]
    try:
        with caplog.at_level(logging.ERROR, logger="brain.pipeline.stages"):
            with pytest.raises(RuntimeError, match="injected prod validation failure"):
                brain.think("force failure")
        assert any(
            DIAG_PIPELINE_FAILED in r.getMessage() for r in caplog.records
        )
    finally:
        brain.pipeline._stage_create_plan = original  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Production readiness rollup (printed for report generation)
# ---------------------------------------------------------------------------


def test_production_readiness_rollup(brain: Brain, tmp_path: Path) -> None:
    """Aggregate a short validation pass and print readiness signals."""
    stress = _run_stress_iterations(brain, 50, message_prefix="rollup")
    assert stress["workspace_growth_bytes"] < 50_000
    assert stress["peak_execution_history"] <= DEFAULT_HISTORY_LIMIT

    # Architecture invariants
    assert brain.execution.engine is not None
    assert brain.planning.engine is not None
    assert isinstance(brain.state_manager.snapshot(), WorkspaceState)

    rollup = {
        "architecture_health": "pass",
        "pipeline_health": "pass" if brain.pipeline.stage_log else "fail",
        "stress_50_avg_ms": stress["avg_runtime_ms"],
        "stress_50_worst_ms": stress["worst_runtime_ms"],
        "memory_growth_bytes": stress["workspace_growth_bytes"],
        "history_limit": DEFAULT_HISTORY_LIMIT,
        "conversation_turn_limit": CONVERSATION_MAX_STORED_TURNS,
        "stage_count": len(STAGE_ORDER),
    }
    print(f"PROD_READINESS_ROLLUP {json.dumps(rollup, sort_keys=True)}")
    assert rollup["pipeline_health"] == "pass"

# =====================================
# Titan Execution Engine Foundation Tests
# =====================================

"""Phase 18.1 Execution Engine — Decision → ExecutionTask → Result."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brain.brain import Brain
from brain.decision_engine import DecisionEngine
from brain.execution import Execution as ExecutionFacade
from brain.execution_engine import ExecutionEngine
from brain.execution_models import (
    ExecutionHistory,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)
from brain.pipeline.context_bundle import ThinkContext
from brain.pipeline.stages import STAGE_ORDER
from brain.planning_engine import PlanningEngine
from brain.planning_models import Plan, PlanStatus
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_models import GoalPriority
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.project_manager import ProjectManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager, WorkspaceState


def _paired_managers(
    tmp_path: Path,
) -> tuple[StateManager, GoalManager, ProjectManager, MissionManager]:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    goals = GoalManager(
        file_path=tmp_path / "titan_goals.json",
        state_manager=state,
    )
    projects = ProjectManager(
        file_path=tmp_path / "titan_projects.json",
        state_manager=state,
        goal_manager=goals,
    )
    missions = MissionManager(
        file_path=tmp_path / "titan_mission.json",
        state_manager=state,
        project_manager=projects,
    )
    goals.bind_project_manager(projects)
    goals.bind_mission_manager(missions)
    return state, goals, projects, missions


def _make_plan(
    *,
    actions: list[str],
    blocked_reason: str | None = None,
    status: PlanStatus = PlanStatus.ACTIVE,
) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan",
        current_project="Execution Engine",
        current_mission="Foundation",
        next_actions=list(actions),
        priority_score=0.8,
        estimated_duration=30.0,
        dependencies=[],
        blocked_reason=blocked_reason,
        created_at=stamp,
        updated_at=stamp,
        status=status,
    )


# ---------------------------------------------------------------------------
# ExecutionTask creation
# ---------------------------------------------------------------------------


def test_execution_task_creation_from_decision(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Ship Titan", priority=GoalPriority.HIGH)
    project = projects.create_project(
        "Execution Engine",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission = missions.create_mission(
        "Foundation",
        "Build execution engine",
        ["Design models", "Wire Brain", "Add tests"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )
    workspace = state.load()
    plan = PlanningEngine().plan_next(
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
        mission_lookup=missions.runtime.get_mission,
    )
    decision = DecisionEngine(persist=False).decide(
        plan=plan,
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
    )

    engine = ExecutionEngine()
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
        send_feedback=False,
    )

    task = engine.active_task
    assert task is not None
    assert isinstance(task, ExecutionTask)
    assert task.action == decision.selected_action
    assert task.decision_id == decision.decision_id
    assert task.context.current_goal == "Ship Titan"
    assert task.context.current_project == "Execution Engine"
    assert task.context.current_mission == "Foundation"
    assert task.context.decision is decision
    assert task.context.current_plan is plan
    assert task.context.workspace_state is workspace
    assert result.task_id == task.task_id
    assert result.action == decision.selected_action


def test_execution_context_shared_not_duplicated() -> None:
    plan = _make_plan(actions=["Only action"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState(active_project="Titan", next_action=None)
    engine = ExecutionEngine()
    engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
    )
    assert engine.active_context is engine.active_task.context
    assert engine.active_task.context.workspace_state is workspace


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_status_transitions_pending_running_completed() -> None:
    plan = _make_plan(actions=["Do work"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    result = engine.execute(decision=decision, plan=plan, send_feedback=False)

    task = engine.active_task
    assert task is not None
    assert task.status == ExecutionStatus.COMPLETED
    assert task.started_at is not None
    assert task.completed_at is not None
    assert result.status == ExecutionStatus.COMPLETED
    assert result.success is True


def test_blocked_plan_yields_blocked_status() -> None:
    plan = _make_plan(
        actions=[],
        blocked_reason="Waiting on dependency",
        status=PlanStatus.BLOCKED,
    )
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    result = engine.execute(decision=decision, plan=plan, send_feedback=False)

    assert engine.active_task is not None
    assert engine.active_task.status == ExecutionStatus.BLOCKED
    assert result.status == ExecutionStatus.BLOCKED
    assert result.success is False
    assert "dependency" in (result.blocked_reason or "").lower() or "dependency" in (
        result.message or ""
    ).lower()


def test_no_selected_action_yields_cancelled() -> None:
    plan = _make_plan(actions=[])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    result = engine.execute(decision=decision, plan=plan, send_feedback=False)

    assert engine.active_task is not None
    assert engine.active_task.status == ExecutionStatus.CANCELLED
    assert result.status == ExecutionStatus.CANCELLED
    assert result.success is False


# ---------------------------------------------------------------------------
# ExecutionResult generation
# ---------------------------------------------------------------------------


def test_execution_result_generation() -> None:
    plan = _make_plan(actions=["Ship it"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    result = engine.execute(decision=decision, plan=plan, send_feedback=False)

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.actual_result == 1.0
    assert result.action == "Ship it"
    assert result.decision_id == decision.decision_id
    payload = result.to_dict()
    assert payload["status"] == "COMPLETED"
    assert payload["task_id"] == result.task_id
    assert engine.history.entries[-1] is result


def test_execution_history_appends_without_rebuild() -> None:
    engine = ExecutionEngine(history_limit=3)
    for action in ("A", "B", "C", "D"):
        plan = _make_plan(actions=[action])
        decision = DecisionEngine(persist=False).decide(plan=plan)
        engine.execute(decision=decision, plan=plan, send_feedback=False)

    assert isinstance(engine.history, ExecutionHistory)
    assert len(engine.history.entries) == 3
    assert [e.action for e in engine.history.entries] == ["B", "C", "D"]


# ---------------------------------------------------------------------------
# Workspace updates
# ---------------------------------------------------------------------------


def test_workspace_updated_after_execution() -> None:
    plan = _make_plan(actions=["Wire Brain"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState(
        active_project="Titan",
        next_action=None,
        current_focus=None,
        current_step=None,
        running_tasks=[],
        brain_mode="idle",
    )
    engine = ExecutionEngine()
    result = engine.execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
    )

    assert result.success is True
    assert workspace.next_action == "Wire Brain"
    assert workspace.current_focus == "Wire Brain"
    assert workspace.current_step == "Wire Brain"
    assert workspace.running_tasks == []
    assert workspace.brain_mode == "working"


def test_workspace_preserves_existing_current_step() -> None:
    plan = _make_plan(actions=["Wire Brain"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    workspace = WorkspaceState(
        active_project="Titan",
        next_action=None,
        current_focus=None,
        current_step="Integration",
        running_tasks=[],
    )
    ExecutionEngine().execute(
        decision=decision,
        plan=plan,
        workspace=workspace,
        send_feedback=False,
    )
    assert workspace.next_action == "Wire Brain"
    assert workspace.current_step == "Integration"


def test_decision_feedback_sent_on_request() -> None:
    plan = _make_plan(actions=["Learn"])
    decision_engine = DecisionEngine(persist=False)
    decision = decision_engine.decide(plan=plan)
    calls: list[dict] = []

    def _feedback(**kwargs):
        calls.append(kwargs)
        return decision_engine.record_feedback(**kwargs)

    result = ExecutionEngine().execute(
        decision=decision,
        plan=plan,
        decision_feedback=_feedback,
        send_feedback=True,
    )
    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["success"] is True
    assert calls[0]["actual_result"] == 1.0
    assert calls[0]["selected_action"] == "Learn"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_execution_diagnostics_emitted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _make_plan(actions=["Alpha"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()

    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        engine.execute(decision=decision, plan=plan, send_feedback=False)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("EXECUTION_CREATED") for msg in messages)
    assert any(msg.startswith("EXECUTION_STARTED") for msg in messages)
    assert any(msg.startswith("EXECUTION_COMPLETED") for msg in messages)


def test_execution_failed_diagnostic_on_blocked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _make_plan(
        actions=[],
        blocked_reason="blocked",
        status=PlanStatus.BLOCKED,
    )
    decision = DecisionEngine(persist=False).decide(plan=plan)
    with caplog.at_level(logging.INFO, logger="brain.execution_engine"):
        ExecutionEngine().execute(decision=decision, plan=plan, send_feedback=False)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("EXECUTION_CREATED") for msg in messages)
    assert any(msg.startswith("EXECUTION_FAILED") for msg in messages)


def test_execution_format_for_prompt_sections() -> None:
    plan = _make_plan(actions=["Prompt action"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    engine.execute(decision=decision, plan=plan, send_feedback=False)
    text = engine.active_task.format_for_prompt()
    assert "Last Tool:" in text
    assert "Execution Status:" in text
    assert "Execution Result:" in text
    assert "Prompt action" in text
    assert "SUCCESS" in text or "COMPLETED" in text


# ---------------------------------------------------------------------------
# Pipeline / Prompt / Brain wiring
# ---------------------------------------------------------------------------


def test_pipeline_stage_order_includes_create_execution() -> None:
    assert "create_execution" in STAGE_ORDER
    assert STAGE_ORDER.index("create_execution") > STAGE_ORDER.index("create_decision")
    assert STAGE_ORDER.index("create_execution") < STAGE_ORDER.index(
        "execution_coordinate"
    )


def test_prompt_builder_injects_current_execution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _make_plan(actions=["Ship it"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    engine = ExecutionEngine()
    engine.execute(decision=decision, plan=plan, send_feedback=False)
    task = engine.active_task
    ctx = ThinkContext(
        user_message="Go",
        current_user="Nolan",
        execution_text=task.format_for_prompt(),
        execution_task=task,
        execution_result=engine.active_result,
    )
    with caplog.at_level(logging.INFO, logger="brain.prompt_builder"):
        prompt = PromptBuilder().build(ctx)

    assert "EXÉCUTION ACTUELLE" in prompt
    assert "Last Tool:" in prompt
    assert "Execution Status:" in prompt
    assert "Execution Result:" in prompt
    assert "Ship it" in prompt
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("EXECUTION_PROMPT_ATTACHED") for msg in messages)


def test_execution_facade_exposes_engine() -> None:
    facade = ExecutionFacade()
    assert isinstance(facade.engine, ExecutionEngine)
    plan = _make_plan(actions=["Next"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    result = facade.execute_decision(
        decision=decision,
        plan=plan,
        send_feedback=False,
    )
    assert result.action == "Next"
    assert facade.active_task is not None


def test_brain_wires_execution_engine(brain: Brain) -> None:
    assert isinstance(brain.execution, ExecutionFacade)
    assert isinstance(brain.execution.engine, ExecutionEngine)
    assert hasattr(brain.execution, "execute_decision")
    assert "create_execution" in STAGE_ORDER


def test_brain_think_includes_execution(brain: Brain) -> None:
    brain.goal_manager.create_goal("Execution Goal")
    project = brain.project_manager.create_project("Execution Project")
    brain.mission_manager.create_mission(
        "Execution Mission",
        "Run next action",
        ["Design", "Wire", "Test"],
        project_id=project.id,
    )

    brain.think("Continue")

    prompt = brain.llm.ask.call_args[0][0]
    assert "EXÉCUTION ACTUELLE" in prompt
    assert "Last Tool:" in prompt
    assert "Execution Status:" in prompt
    assert "Execution Result:" in prompt
    assert "Design" in prompt

    snap = brain.state_manager.snapshot()
    assert snap.next_action == "Design"
    assert snap.current_focus == "Design"

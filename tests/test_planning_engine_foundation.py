# =====================================
# Titan Planning Engine Foundation Tests
# =====================================

"""Phase 17.1 Planning Engine — next-action plan from Goal / Project / Mission."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from brain.brain import Brain
from brain.pipeline.context_bundle import ThinkContext
from brain.planner import Planner
from brain.planning_engine import PlanningEngine
from brain.planning_models import (
    Plan,
    PlanStatus,
    compute_priority_score,
    priority_weight,
)
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_models import GoalPriority
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority, MissionState
from core.project_manager import ProjectManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager


REQUIRED_PLAN_FIELDS = {
    "current_goal",
    "current_project",
    "current_mission",
    "next_actions",
    "priority_score",
    "estimated_duration",
    "dependencies",
    "blocked_reason",
    "created_at",
    "updated_at",
    "revision",
    "change_reason",
    "latest_changes",
}


def _assert_required_fields(plan: Plan) -> None:
    payload = plan.to_dict()
    assert REQUIRED_PLAN_FIELDS.issubset(payload.keys())


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


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------


def test_plan_generation_from_workspace_hierarchy(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Ship Titan", priority=GoalPriority.HIGH)
    project = projects.create_project(
        "Planning Engine",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission = missions.create_mission(
        "Foundation",
        "Build next-action planner",
        ["Design models", "Wire Brain", "Add tests"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )

    engine = PlanningEngine()
    plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
        mission_lookup=missions.runtime.get_mission,
    )

    _assert_required_fields(plan)
    assert plan.current_goal == "Ship Titan"
    assert plan.current_project == "Planning Engine"
    assert plan.current_mission == "Foundation"
    assert plan.next_actions[0] == "Design models"
    assert "Wire Brain" in plan.next_actions
    assert plan.priority_score > 0.5
    assert plan.estimated_duration is not None
    assert plan.estimated_duration > 0
    assert plan.status == PlanStatus.ACTIVE
    assert plan.blocked_reason is None


def test_plan_format_for_prompt_includes_required_sections(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Focus Goal")
    project = projects.create_project("Focus Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Focus Mission",
        steps=["Do the thing"],
        project_id=project.id,
    )
    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    text = plan.format_for_prompt()
    assert "Current Plan:" in text
    assert "Next Actions:" in text
    assert "Priority:" in text
    assert "Blocked Reason:" in text
    assert "Plan Revision:" in text
    assert "Latest Changes:" in text
    assert "Do the thing" in text


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


def test_priority_ordering_critical_outranks_low() -> None:
    low = compute_priority_score(
        importance=priority_weight("LOW"),
        urgency=priority_weight("LOW"),
        manual_priority=priority_weight("LOW"),
    )
    critical = compute_priority_score(
        importance=priority_weight("CRITICAL"),
        urgency=priority_weight("CRITICAL"),
        manual_priority=priority_weight("CRITICAL"),
    )
    assert critical > low


def test_priority_blocked_caps_score() -> None:
    open_score = compute_priority_score(
        importance=1.0,
        urgency=1.0,
        manual_priority=1.0,
        is_blocked=False,
    )
    blocked_score = compute_priority_score(
        importance=1.0,
        urgency=1.0,
        manual_priority=1.0,
        is_blocked=True,
    )
    assert blocked_score < open_score
    assert blocked_score <= 0.35


def test_priority_ordering_across_missions(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Priority Goal", priority=GoalPriority.NORMAL)
    project = projects.create_project(
        "Priority Project",
        priority=ProjectPriority.NORMAL,
        goal_id=goal.id,
    )
    low_mission = missions.create_mission(
        "Low Mission",
        steps=["A"],
        priority=MissionPriority.LOW,
        project_id=project.id,
    )
    missions.pause_mission(low_mission.id)
    critical_mission = missions.create_mission(
        "Critical Mission",
        steps=["B"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )

    engine = PlanningEngine()
    low_plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=low_mission,
    )
    critical_plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=critical_mission,
    )
    assert critical_plan.priority_score > low_plan.priority_score


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def test_dependencies_include_parent_and_later_steps(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Deps Goal")
    project = projects.create_project("Deps Project", goal_id=goal.id)
    parent = missions.create_mission(
        "Parent Mission",
        steps=["Parent work"],
        project_id=project.id,
    )
    child = missions.create_mission(
        "Child Mission",
        steps=["Child A", "Child B"],
        parent_mission=parent.id,
        project_id=project.id,
    )

    plan = Planner().build(
        workspace=state.load(),
        mission=child,
        mission_lookup=missions.runtime.get_mission,
    )
    assert any(dep.startswith(f"parent_mission:{parent.id}") for dep in plan.dependencies)
    assert "step:Child B" in plan.dependencies


def test_unmet_parent_dependency_blocks_plan(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Block Deps")
    project = projects.create_project("Block Project", goal_id=goal.id)
    parent = missions.create_mission(
        "Unfinished Parent",
        steps=["Still open"],
        project_id=project.id,
    )
    child = missions.create_mission(
        "Waiting Child",
        steps=["Child step"],
        parent_mission=parent.id,
        project_id=project.id,
    )

    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=child,
        mission_lookup=missions.runtime.get_mission,
    )
    assert plan.is_blocked
    assert plan.status == PlanStatus.BLOCKED
    assert plan.blocked_reason is not None
    assert "dependency" in plan.blocked_reason.lower()
    assert plan.next_actions == []


# ---------------------------------------------------------------------------
# Blocked plans
# ---------------------------------------------------------------------------


def test_blocked_mission_state_produces_blocked_plan(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Blocked Goal")
    project = projects.create_project("Blocked Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Blocked Mission",
        steps=["Cannot proceed"],
        state=MissionState.BLOCKED,
        notes="Waiting on API key",
        project_id=project.id,
    )

    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert plan.status == PlanStatus.BLOCKED
    assert plan.is_blocked
    assert plan.next_actions == []
    assert plan.blocked_reason is not None
    assert "API key" in plan.blocked_reason or "BLOCKED" in plan.blocked_reason


def test_plan_blocked_diagnostic_emitted(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Diag Goal")
    project = projects.create_project("Diag Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Diag Blocked",
        steps=["X"],
        state=MissionState.BLOCKED,
        project_id=project.id,
    )

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        PlanningEngine().plan_next(
            workspace=state.load(),
            goal=goal,
            project=project,
            mission=mission,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_CREATED") for msg in messages)
    assert any(msg.startswith("PLAN_BLOCKED") for msg in messages)


# ---------------------------------------------------------------------------
# Plan completion
# ---------------------------------------------------------------------------


def test_complete_plan_marks_completed_and_emits_diagnostic(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Done Goal")
    project = projects.create_project("Done Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Done Mission",
        steps=["Finish"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        completed = engine.complete_plan(plan)

    assert completed.status == PlanStatus.COMPLETED
    assert completed.is_completed
    assert completed.next_actions == []
    assert engine.active_plan is completed
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_COMPLETED") for msg in messages)


def test_completed_mission_yields_completed_plan(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Complete Goal")
    project = projects.create_project("Complete Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Already Done",
        steps=["One"],
        project_id=project.id,
    )
    missions.complete_mission(mission.id)
    mission = missions.runtime.get_mission(mission.id)
    assert mission is not None

    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert plan.status == PlanStatus.COMPLETED
    assert plan.next_actions == []


# ---------------------------------------------------------------------------
# Performance — single WorkspaceState read, no duplicated planning
# ---------------------------------------------------------------------------


def test_single_workspace_read_for_plan_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Read Once")
    project = projects.create_project("Read Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Read Mission",
        steps=["Step"],
        project_id=project.id,
    )

    load_count = {"n": 0}
    original_load = state.load

    def counted_load(*args, **kwargs):
        load_count["n"] += 1
        return original_load(*args, **kwargs)

    monkeypatch.setattr(state, "load", counted_load)
    workspace = state.load()
    assert load_count["n"] == 1

    PlanningEngine().plan_next(
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
    )
    assert load_count["n"] == 1


def test_plan_refreshed_on_same_focus_unchanged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Update Goal")
    project = projects.create_project("Update Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Update Mission",
        steps=["First", "Second"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    workspace = state.load()

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        first = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
        )
        second = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
        )

    assert first.created_at == second.created_at
    assert first.revision == second.revision
    assert second.updated_at >= first.updated_at
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_CREATED") for msg in messages)
    assert any(msg.startswith("PLAN_REFRESHED") for msg in messages)
    assert any(msg.startswith("PLAN_REVISION") for msg in messages)


# ---------------------------------------------------------------------------
# Prompt builder + Brain wiring
# ---------------------------------------------------------------------------


def test_prompt_builder_injects_current_plan() -> None:
    empty = Plan.empty()
    plan = Plan(
        current_goal="G",
        current_project="P",
        current_mission="M",
        next_actions=["Act"],
        priority_score=0.8,
        estimated_duration=15.0,
        dependencies=[],
        blocked_reason=None,
        created_at=empty.created_at,
        updated_at=empty.updated_at,
        status=PlanStatus.ACTIVE,
        revision=2,
        change_reason="workspace_changed",
        latest_changes=["workspace_changed", "next_actions updated"],
    )
    ctx = ThinkContext(
        user_message="Continue",
        structured_plan_text=plan.format_for_prompt(),
        execution_plan=plan,
    )
    prompt = PromptBuilder().build(ctx)
    assert "PLAN D'ACTION" in prompt
    assert "Current Plan:" in prompt
    assert "Next Actions:" in prompt
    assert "Priority:" in prompt
    assert "Blocked Reason:" in prompt
    assert "Plan Revision:" in prompt
    assert "Latest Changes:" in prompt
    assert "Act" in prompt
    assert "2" in prompt
    assert "workspace_changed" in prompt


def test_brain_think_includes_execution_plan(brain: Brain) -> None:
    brain.goal_manager.create_goal("Brain Goal")
    project = brain.project_manager.create_project("Brain Project")
    brain.mission_manager.create_mission(
        "Trading",
        "NQ bot",
        ["Backtest", "Live"],
        project_id=project.id,
    )

    brain.think("Continue le backtest")

    prompt = brain.llm.ask.call_args[0][0]
    assert "PLAN D'ACTION" in prompt
    assert "Current Plan:" in prompt
    assert "Backtest" in prompt
    assert "Next Actions:" in prompt
    assert "Priority:" in prompt


# ---------------------------------------------------------------------------
# Phase 8 regression — StructuredPlan API still works
# ---------------------------------------------------------------------------


def test_phase8_structured_plan_api_preserved() -> None:
    engine = PlanningEngine()
    structured = engine.create_plan(
        "Continue le backtest",
        mission={
            "active": True,
            "title": "Trading",
            "objective": "NQ",
            "current_step": "Backtest",
        },
    )
    assert structured.mission_step == "Backtest"
    assert "Backtest" in structured.format_for_prompt()

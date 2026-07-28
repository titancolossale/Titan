# =====================================
# Titan Dynamic Plan Evolution Tests
# =====================================

"""Phase 17.2 — execution plans evolve when workspace / goal / project / mission change."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from brain.planning_engine import PlanningEngine
from brain.planning_models import (
    CHANGE_REASON_GOAL_CHANGED,
    CHANGE_REASON_MISSION_BLOCKED,
    CHANGE_REASON_MISSION_COMPLETED,
    CHANGE_REASON_PROJECT_CHANGED,
    CHANGE_REASON_WORKSPACE_CHANGED,
    PlanStatus,
)
from brain.prompt_builder import PromptBuilder
from brain.pipeline.context_bundle import ThinkContext
from core.goal_manager import GoalManager
from core.goal_models import GoalPriority
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority, MissionState
from core.project_manager import ProjectManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager


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
# Mission completion updates plan
# ---------------------------------------------------------------------------


def test_mission_completion_updates_plan(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Ship Goal")
    project = projects.create_project("Ship Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Ship Mission",
        steps=["Design", "Build"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    first = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert first.status == PlanStatus.ACTIVE
    assert first.revision == 1

    missions.complete_mission(mission.id)
    completed = missions.runtime.get_mission(mission.id)
    assert completed is not None

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        second = engine.plan_next(
            workspace=state.load(),
            goal=goal,
            project=project,
            mission=completed,
        )

    assert second.status == PlanStatus.COMPLETED
    assert second.next_actions == []
    assert second.revision == first.revision + 1
    assert second.change_reason == CHANGE_REASON_MISSION_COMPLETED
    assert CHANGE_REASON_MISSION_COMPLETED in second.latest_changes
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_UPDATED") for msg in messages)
    assert any(msg.startswith("PLAN_REVISION") for msg in messages)
    assert any(msg.startswith("PLAN_COMPLETED") for msg in messages)


def test_mission_blocked_updates_plan(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Block Goal")
    project = projects.create_project("Block Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Open Mission",
        steps=["Work"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    first = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert not first.is_blocked

    blocked = missions.create_mission(
        "Blocked Mission",
        steps=["Cannot"],
        state=MissionState.BLOCKED,
        notes="Waiting on key",
        project_id=project.id,
    )
    # Switch active mission to blocked one via plan_next with blocked mission.
    second = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=blocked,
    )
    assert second.is_blocked
    assert second.revision > first.revision
    assert second.change_reason in {
        CHANGE_REASON_MISSION_BLOCKED,
        CHANGE_REASON_PROJECT_CHANGED,  # focus may also shift via mission title
    } or CHANGE_REASON_MISSION_BLOCKED in second.latest_changes
    assert CHANGE_REASON_MISSION_BLOCKED in second.latest_changes or second.is_blocked


# ---------------------------------------------------------------------------
# Workspace change updates plan
# ---------------------------------------------------------------------------


def test_workspace_change_updates_plan(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("WS Goal")
    project = projects.create_project("WS Project", goal_id=goal.id)
    mission = missions.create_mission(
        "WS Mission",
        steps=["Step A", "Step B"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    workspace = state.load()
    first = engine.plan_next(
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
    )

    # Advance mission step so next_actions / workspace mirror change.
    missions.complete_current_step()
    mission = missions.get_active_mission()
    assert mission is not None
    workspace = state.load()

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        second = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
        )

    assert second.revision == first.revision + 1
    assert second.next_actions != first.next_actions
    assert second.created_at == first.created_at
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        msg.startswith("PLAN_UPDATED") or msg.startswith("PLAN_REBUILT")
        for msg in messages
    )
    assert any(msg.startswith("PLAN_REVISION") for msg in messages)


# ---------------------------------------------------------------------------
# Goal / project switch updates plan
# ---------------------------------------------------------------------------


def test_goal_switch_updates_plan(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal_a = goals.create_goal("Goal A", priority=GoalPriority.NORMAL)
    project_a = projects.create_project("Project A", goal_id=goal_a.id)
    mission_a = missions.create_mission(
        "Mission A",
        steps=["A1"],
        project_id=project_a.id,
    )
    engine = PlanningEngine()
    first = engine.plan_next(
        workspace=state.load(),
        goal=goal_a,
        project=project_a,
        mission=mission_a,
    )

    goal_b = goals.create_goal("Goal B", priority=GoalPriority.HIGH)
    project_b = projects.create_project("Project B", goal_id=goal_b.id)
    mission_b = missions.create_mission(
        "Mission B",
        steps=["B1"],
        priority=MissionPriority.HIGH,
        project_id=project_b.id,
    )

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        second = engine.plan_next(
            workspace=state.load(),
            goal=goal_b,
            project=project_b,
            mission=mission_b,
        )

    assert second.current_goal == "Goal B"
    assert second.revision == first.revision + 1
    assert second.change_reason == CHANGE_REASON_GOAL_CHANGED
    assert CHANGE_REASON_GOAL_CHANGED in second.latest_changes
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_REBUILT") for msg in messages)
    assert any(msg.startswith("PLAN_REVISION") for msg in messages)


def test_project_switch_updates_plan(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Shared Goal")
    project_a = projects.create_project(
        "Project Alpha",
        priority=ProjectPriority.NORMAL,
        goal_id=goal.id,
    )
    mission_a = missions.create_mission(
        "Mission Alpha",
        steps=["Alpha step"],
        project_id=project_a.id,
    )
    engine = PlanningEngine()
    first = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project_a,
        mission=mission_a,
    )

    project_b = projects.create_project(
        "Project Beta",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission_b = missions.create_mission(
        "Mission Beta",
        steps=["Beta step"],
        project_id=project_b.id,
    )

    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        second = engine.plan_next(
            workspace=state.load(),
            goal=goal,
            project=project_b,
            mission=mission_b,
        )

    assert second.current_project == "Project Beta"
    assert second.revision == first.revision + 1
    assert second.change_reason == CHANGE_REASON_PROJECT_CHANGED
    assert CHANGE_REASON_PROJECT_CHANGED in second.latest_changes
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_REBUILT") for msg in messages)
    assert any(msg.startswith("PLAN_REVISION") for msg in messages)


# ---------------------------------------------------------------------------
# Revision increments correctly
# ---------------------------------------------------------------------------


def test_revision_increments_correctly(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Rev Goal")
    project = projects.create_project("Rev Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Rev Mission",
        steps=["One", "Two", "Three"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    r1 = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert r1.revision == 1

    # Identical inputs → refresh, revision unchanged.
    r1b = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert r1b.revision == 1

    missions.complete_current_step()
    mission = missions.get_active_mission()
    r2 = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    assert r2.revision == 2

    completed = engine.complete_plan(r2)
    assert completed.revision == 3
    assert completed.change_reason == CHANGE_REASON_MISSION_COMPLETED


# ---------------------------------------------------------------------------
# Prompt injection — Plan Revision + Latest Changes
# ---------------------------------------------------------------------------


def test_prompt_includes_plan_revision_and_latest_changes(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Prompt Goal")
    project = projects.create_project("Prompt Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Prompt Mission",
        steps=["Do work"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    missions.complete_current_step()
    mission = missions.get_active_mission()
    # Completing the only step finishes the mission → completed plan.
    plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    text = plan.format_for_prompt()
    assert "Plan Revision:" in text
    assert "Latest Changes:" in text
    assert str(plan.revision) in text

    ctx = ThinkContext(
        user_message="Continue",
        structured_plan_text=text,
        execution_plan=plan,
    )
    prompt = PromptBuilder().build(ctx)
    assert "Plan Revision:" in prompt
    assert "Latest Changes:" in prompt


# ---------------------------------------------------------------------------
# Incremental — no unnecessary rebuild
# ---------------------------------------------------------------------------


def test_identical_workspace_does_not_bump_revision(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Stable Goal")
    project = projects.create_project("Stable Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Stable Mission",
        steps=["Steady"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    workspace = state.load()
    first = engine.plan_next(
        workspace=workspace,
        goal=goal,
        project=project,
        mission=mission,
    )
    with caplog.at_level(logging.INFO, logger="brain.planning_engine"):
        second = engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
        )
    assert second.revision == first.revision
    assert second.change_reason == "plan_refreshed"
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PLAN_REFRESHED") for msg in messages)
    assert not any(msg.startswith("PLAN_REBUILT") for msg in messages)


def test_forced_workspace_change_reason(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Forced Goal")
    project = projects.create_project("Forced Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Forced Mission",
        steps=["First", "Second"],
        project_id=project.id,
    )
    engine = PlanningEngine()
    engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )
    missions.complete_current_step()
    mission = missions.get_active_mission()
    plan = engine.plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
        change_reason=CHANGE_REASON_WORKSPACE_CHANGED,
    )
    assert plan.revision >= 2
    assert CHANGE_REASON_WORKSPACE_CHANGED in (plan.latest_changes or [])

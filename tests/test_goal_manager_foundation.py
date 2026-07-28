# =====================================
# Titan Goal Manager Foundation Tests
# =====================================

"""Phase 16.1 GoalManager / Goal foundation tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from brain.brain import Brain
from brain.pipeline.context_bundle import GoalContext, MissionContext, ProjectContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_models import Goal, GoalPriority, GoalState
from core.mission_manager import MissionManager
from core.project_manager import ProjectManager
from core.project_models import ProjectState
from core.state_manager import StateManager, WorkspaceState


REQUIRED_GOAL_FIELDS = {
    "id",
    "name",
    "description",
    "status",
    "priority",
    "created_at",
    "updated_at",
    "progress",
    "project_ids",
    "active_project_id",
    "aliases",
    "keywords",
}


def _assert_required_fields(goal: Goal | dict) -> None:
    payload = goal.to_dict() if isinstance(goal, Goal) else goal
    assert REQUIRED_GOAL_FIELDS.issubset(payload.keys())


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
# Goal creation
# ---------------------------------------------------------------------------


def test_create_goal_returns_foundation_fields(tmp_path: Path) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    goal = manager.create_goal(
        name="Build Titan OS",
        description="Personal agentic AI platform",
        priority=GoalPriority.HIGH,
    )

    _assert_required_fields(goal)
    assert goal.name == "Build Titan OS"
    assert goal.description == "Personal agentic AI platform"
    assert goal.status == GoalState.ACTIVE.value
    assert goal.priority == GoalPriority.HIGH
    assert goal.progress == 0.0
    assert goal.active_project_id is None
    assert goal.project_ids == []
    assert manager.get_active_goal() is not None
    assert manager.get_active_goal().id == goal.id


def test_goal_persistence_round_trip(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_goals.json"
    manager = GoalManager(file_path=file_path)
    created = manager.create_goal("Persist Me", "Durable")

    reloaded = GoalManager(file_path=file_path)
    loaded = reloaded.get_goal(created.id)
    assert loaded is not None
    assert loaded.name == "Persist Me"
    assert loaded.description == "Durable"
    assert loaded.status == GoalState.ACTIVE.value
    assert reloaded.get_active_goal() is not None
    assert reloaded.get_active_goal().id == created.id

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert created.id in on_disk["goals"]
    assert on_disk["active_goal_id"] == created.id


def test_multiple_goals_single_active(tmp_path: Path) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    first = manager.create_goal("Alpha")
    second = manager.create_goal("Beta")

    assert len(manager.list_goals()) == 2
    active = manager.get_active_goal()
    assert active is not None
    assert active.id == second.id
    assert active.status == GoalState.ACTIVE.value

    paused = manager.get_goal(first.id)
    assert paused is not None
    assert paused.status == GoalState.PAUSED.value


def test_active_goal_switching(tmp_path: Path) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    first = manager.create_goal("Alpha")
    second = manager.create_goal("Beta")

    resumed = manager.resume_goal(first.id)
    assert resumed.status == GoalState.ACTIVE.value
    assert manager.get_active_goal().id == first.id

    other = manager.get_goal(second.id)
    assert other is not None
    assert other.status == GoalState.PAUSED.value


def test_pause_complete_archive_delete(tmp_path: Path) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    created = manager.create_goal("Lifecycle")

    paused = manager.pause_goal(created.id)
    assert paused.status == GoalState.PAUSED.value
    assert manager.get_active_goal() is None

    resumed = manager.resume_goal(created.id)
    assert resumed.status == GoalState.ACTIVE.value

    completed = manager.complete_goal(created.id)
    assert completed.status == GoalState.COMPLETED.value
    assert completed.progress == 100.0
    assert manager.get_active_goal() is None

    other = manager.create_goal("Archive Target")
    archived = manager.archive_goal(other.id)
    assert archived.status == GoalState.ARCHIVED.value

    manager.delete_goal(other.id)
    assert manager.get_goal(other.id) is None


def test_workspace_state_mirrors_goals(tmp_path: Path) -> None:
    state, goals, _projects, _missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Mirror Me", "Sync")

    snap = state.snapshot()
    assert snap.active_goal_id == goal.id
    assert snap.active_goal == "Mirror Me"
    assert snap.active_goal_status == GoalState.ACTIVE.value
    assert snap.active_goal_progress == 0.0
    assert isinstance(snap.goals, list)
    assert len(snap.goals) == 1
    assert snap.goals[0]["id"] == goal.id
    assert snap.goals[0]["name"] == "Mirror Me"


# ---------------------------------------------------------------------------
# Project ownership
# ---------------------------------------------------------------------------


def test_project_belongs_to_goal(tmp_path: Path) -> None:
    _state, goals, projects, _missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Owner")

    project = projects.create_project(
        "Owned Project",
        "Under goal",
        goal_id=goal.id,
    )

    assert project.goal_id == goal.id
    owned = goals.get_goal(goal.id)
    assert owned is not None
    assert project.id in owned.project_ids
    assert owned.active_project_id == project.id


def test_project_defaults_to_active_goal(tmp_path: Path) -> None:
    _state, goals, projects, _missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Default Owner")

    project = projects.create_project("Auto Owned")
    assert project.goal_id == goal.id


def test_project_rejects_unknown_goal(tmp_path: Path) -> None:
    _state, _goals, projects, _missions = _paired_managers(tmp_path)

    with pytest.raises(ValueError, match="Unknown goal id"):
        projects.create_project(
            "Orphan",
            goal_id="does-not-exist",
        )


def test_project_requires_goal_when_manager_bound(tmp_path: Path) -> None:
    """Without an active goal, ProjectManager auto-creates a default owner."""
    _state, goals, projects, _missions = _paired_managers(tmp_path)
    goals.pause_goal(goals.create_goal("Temp").id)

    project = projects.create_project("Auto Default Owner")
    assert project.goal_id is not None
    owner = goals.get_goal(project.goal_id)
    assert owner is not None
    assert owner.status == GoalState.ACTIVE.value
    assert project.id in owner.project_ids


# ---------------------------------------------------------------------------
# Brain awareness
# ---------------------------------------------------------------------------


def test_brain_loads_active_goal(brain: Brain) -> None:
    goal = brain.goal_manager.create_goal(
        "Brain Goal",
        "Phase 16.1",
    )
    project = brain.project_manager.create_project(
        "Brain Project",
        "Under goal",
        goal_id=goal.id,
    )
    brain.mission_manager.create_mission(
        "Brain Mission",
        "Ship it",
        ["Wire", "Test"],
        project_id=project.id,
    )

    brain.think("Quel est le goal actif ?")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_goal_id == goal.id
    assert ctx.workspace_state.active_goal == "Brain Goal"
    assert ctx.goal_context is not None
    assert ctx.goal_context.name == "Brain Goal"
    assert ctx.goal_context.goal_id == goal.id
    assert ctx.project_context is not None
    assert ctx.project_context.project_id == project.id
    assert ctx.mission_context is not None
    assert ctx.mission_context.active_mission == "Brain Mission"


def test_prompt_includes_goal_project_mission_metadata() -> None:
    goal_context = GoalContext(
        name="Ship Titan",
        status="ACTIVE",
        progress=10.0,
        goal_id="goal-1",
        current_project="Titan",
        current_mission="Ship Phase 16.1",
    )
    project_context = ProjectContext(
        name="Titan",
        status="ACTIVE",
        progress=25.0,
        project_id="proj-1",
    )
    mission_context = MissionContext(
        active_mission="Ship Phase 16.1",
        status="RUNNING",
        progress=40.0,
    )
    ctx = ThinkContext(
        user_message="Continue.",
        goal_context=goal_context,
        project_context=project_context,
        mission_context=mission_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONTEXTE GOAL" in prompt
    assert "Current Goal:" in prompt
    assert "Ship Titan" in prompt
    assert "Goal Progress:" in prompt
    assert "Current Project:" in prompt
    assert "Titan" in prompt
    assert "Current Mission:" in prompt
    assert "Ship Phase 16.1" in prompt
    assert "CONTEXTE PROJET" in prompt
    assert "CONTEXTE MISSION" in prompt


def test_goal_diagnostics_emitted(brain: Brain, caplog: Any) -> None:
    with caplog.at_level(logging.INFO):
        goal = brain.goal_manager.create_goal("Diag Goal")
        brain.think("Diagnostics goal")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_CREATED") for msg in messages)
    assert any(msg.startswith("GOAL_LOADED") for msg in messages)
    assert any(msg.startswith("GOAL_CONTEXT_LOADED") for msg in messages)
    assert brain.last_think_context is not None
    assert brain.last_think_context.goal_context is not None
    assert brain.last_think_context.goal_context.goal_id == goal.id


def test_goal_switched_and_completed_diagnostics(
    tmp_path: Path,
    caplog: Any,
) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    first = manager.create_goal("One")

    with caplog.at_level(logging.INFO):
        manager.create_goal("Two")
        manager.complete_goal(first.id)
        other = manager.list_goals(status=GoalState.ACTIVE)[0]
        manager.archive_goal(other.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_SWITCHED") for msg in messages)
    assert any(msg.startswith("GOAL_COMPLETED") for msg in messages)
    assert any(msg.startswith("GOAL_ARCHIVED") for msg in messages)


def test_single_workspace_state_read_for_goal_awareness(brain: Brain) -> None:
    """Goal awareness must come from the one WorkspaceState load in _begin_think."""
    goal = brain.goal_manager.create_goal("Perf Goal")
    load_calls = {"count": 0}
    original_load = brain.state_manager.load

    def counting_load() -> WorkspaceState:
        load_calls["count"] += 1
        return original_load()

    brain.state_manager.load = counting_load  # type: ignore[method-assign]
    brain.think("Check goal load count")

    assert load_calls["count"] == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.goal_id == goal.id
    assert ctx.goal_context.name == "Perf Goal"
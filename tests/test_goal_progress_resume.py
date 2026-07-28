# =====================================
# Titan Goal Progress & Resume Tests
# =====================================

"""Phase 16.2 — goal progress persists and resumes across project/mission changes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import GoalContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_models import GoalState
from core.mission_manager import MissionManager
from core.project_manager import ProjectManager
from core.project_models import ProjectState
from core.state_manager import StateManager, WorkspaceState


def _paired(
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


def test_goal_progress_updates_from_projects(tmp_path: Path) -> None:
    """Goal progress must average contained project progress values."""
    state, goals, projects, _missions = _paired(tmp_path)
    goal = goals.create_goal("Progress Goal")

    first = projects.create_project("Alpha", goal_id=goal.id)
    second = projects.create_project("Beta", goal_id=goal.id)
    projects.update_progress(first.id, 50.0)
    projects.update_progress(second.id, 100.0)

    snapshot = goals.get_progress(goal.id)
    assert snapshot.total_projects == 2
    assert snapshot.completed_projects == 0
    assert abs(snapshot.progress - 75.0) < 0.01
    assert snapshot.last_activity is not None

    reloaded = goals.get_goal(goal.id)
    assert reloaded is not None
    assert abs(reloaded.progress - 75.0) < 0.01

    workspace = state.snapshot()
    assert abs(float(workspace.active_goal_progress or 0) - 75.0) < 0.01
    assert workspace.active_goal_total_projects == 2


def test_project_completion_updates_goal(tmp_path: Path) -> None:
    """Completing a project must refresh goal progress and counts."""
    state, goals, projects, _missions = _paired(tmp_path)
    goal = goals.create_goal("Complete Tracking")
    first = projects.create_project("Done Soon", goal_id=goal.id)
    second = projects.create_project("Still Open", goal_id=goal.id)

    projects.complete_project(first.id)

    snapshot = goals.get_progress(goal.id)
    assert snapshot.completed_projects == 1
    assert snapshot.total_projects == 2
    assert snapshot.active_projects == 1
    assert abs(snapshot.progress - 50.0) < 0.01

    workspace = state.snapshot()
    assert workspace.active_goal_completed_projects == 1
    assert workspace.active_goal_total_projects == 2
    assert abs(float(workspace.active_goal_progress or 0) - 50.0) < 0.01
    active = projects.get_active_project()
    assert active is not None
    assert active.id == second.id


def test_mission_completion_updates_goal(tmp_path: Path) -> None:
    """Completing a mission must refresh owning goal progress."""
    state, goals, projects, missions = _paired(tmp_path)
    goal = goals.create_goal("Mission → Goal")
    project = projects.create_project("Owned", goal_id=goal.id)
    mission = missions.create_mission(
        "Finish Me",
        "Complete tracking",
        ["One"],
        project_id=project.id,
    )

    missions.complete_mission(mission.id)
    projects.update_progress(project.id, 100.0)

    snapshot = goals.get_progress(goal.id)
    assert snapshot.total_projects == 1
    assert abs(snapshot.progress - 100.0) < 0.01

    workspace = state.snapshot()
    assert abs(float(workspace.active_goal_progress or 0) - 100.0) < 0.01


def test_mission_completion_emits_goal_progress(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """Mission completion path must emit GOAL_PROGRESS_UPDATED."""
    _state, goals, projects, missions = _paired(tmp_path)
    goal = goals.create_goal("Diag Progress")
    project = projects.create_project("Diag Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Diag Mission",
        "Emit",
        ["Step"],
        project_id=project.id,
    )

    with caplog.at_level(logging.INFO):
        missions.complete_mission(mission.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_PROGRESS_UPDATED") for msg in messages)


def test_resume_restores_goal_project_mission(tmp_path: Path) -> None:
    """resume_goal must restore current project + mission + workspace mirror."""
    state, goals, projects, missions = _paired(tmp_path)
    goal = goals.create_goal("Resume Me")
    project = projects.create_project("Resume Project", goal_id=goal.id)
    mission = missions.create_mission(
        "Resume Mission",
        "Restore context",
        ["A", "B"],
        project_id=project.id,
    )

    goals.pause_goal(goal.id)
    projects.pause_project(project.id)
    missions.pause_mission(mission.id)

    assert goals.get_active_goal() is None
    assert projects.get_active_project() is None

    resumed = goals.resume_goal(goal.id)

    assert resumed.status == GoalState.ACTIVE.value
    active_goal = goals.get_active_goal()
    assert active_goal is not None
    assert active_goal.id == goal.id

    active_project = projects.get_active_project()
    assert active_project is not None
    assert active_project.id == project.id

    active_mission = missions.get_active_mission()
    assert active_mission is not None
    assert active_mission.id == mission.id

    workspace = state.snapshot()
    assert workspace.active_goal_id == goal.id
    assert workspace.active_goal == "Resume Me"
    assert workspace.active_project_id == project.id
    assert workspace.active_mission_id == mission.id
    assert workspace.active_goal_current_project == "Resume Project"
    assert workspace.active_goal_current_mission in {
        "Resume Mission",
        mission.title,
    }


def test_resume_emits_goal_resumed(tmp_path: Path, caplog: Any) -> None:
    _state, goals, projects, missions = _paired(tmp_path)
    goal = goals.create_goal("Resume Diag")
    project = projects.create_project("P", goal_id=goal.id)
    mission = missions.create_mission("M", "x", ["s"], project_id=project.id)
    goals.pause_goal(goal.id)
    projects.pause_project(project.id)
    missions.pause_mission(mission.id)

    with caplog.at_level(logging.INFO):
        goals.resume_goal(goal.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_RESUMED") for msg in messages)


def test_goal_completed_diagnostic(tmp_path: Path, caplog: Any) -> None:
    manager = GoalManager(file_path=tmp_path / "titan_goals.json")
    goal = manager.create_goal("Done")

    with caplog.at_level(logging.INFO):
        manager.complete_goal(goal.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_COMPLETED") for msg in messages)


def test_prompt_includes_goal_progress_and_resume() -> None:
    goal_context = GoalContext(
        name="Ship Phase 16.2",
        status="ACTIVE",
        progress=42.5,
        goal_id="goal-16-2",
        completed_projects=1,
        active_projects=1,
        paused_projects=0,
        total_projects=2,
        current_project="Progress Project",
        current_mission="Resume Mission",
    )
    ctx = ThinkContext(
        user_message="Continue.",
        goal_context=goal_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONTEXTE GOAL" in prompt
    assert "Current Goal:" in prompt
    assert "Ship Phase 16.2" in prompt
    assert "Goal Progress:" in prompt
    assert "42.5" in prompt
    assert "Current Project:" in prompt
    assert "Progress Project" in prompt
    assert "Current Mission:" in prompt
    assert "Resume Mission" in prompt


def test_brain_think_stamps_goal_progress(brain: Brain) -> None:
    """Successful think must stamp goal resume fields onto WorkspaceState."""
    goal = brain.goal_manager.create_goal("Think Goal")
    project = brain.project_manager.create_project(
        "Think Project",
        goal_id=goal.id,
    )
    brain.mission_manager.create_mission(
        "Think Mission",
        "Stamp",
        ["One", "Two"],
        project_id=project.id,
    )

    brain.think("Continuer le goal")

    snap = brain.state_manager.snapshot()
    assert snap.active_goal_id == goal.id
    assert snap.active_goal == "Think Goal"
    assert snap.active_goal_progress is not None
    assert snap.active_goal_current_project == "Think Project"
    assert snap.active_goal_current_mission == "Think Mission"
    assert snap.active_goal_last_summary
    assert snap.active_goal_progress_updated_at is not None

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.name == "Think Goal"
    assert "Goal Progress:" in ctx.prompt
    assert "Current Project:" in ctx.prompt
    assert "Current Mission:" in ctx.prompt


def test_goal_progress_diagnostics_on_think(brain: Brain, caplog: Any) -> None:
    goal = brain.goal_manager.create_goal("Diag Think Goal")
    project = brain.project_manager.create_project("Diag P", goal_id=goal.id)
    brain.mission_manager.create_mission(
        "Diag M",
        "x",
        ["s"],
        project_id=project.id,
    )

    with caplog.at_level(logging.INFO):
        brain.think("Diagnostics goal progress")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_PROGRESS_UPDATED") for msg in messages)
    assert any(msg.startswith("GOAL_RESUME_LOADED") for msg in messages)
    assert any(msg.startswith("GOAL_RESUME_INJECTED") for msg in messages)


def test_goal_context_from_workspace() -> None:
    active = WorkspaceState(
        active_goal="From State",
        active_goal_id="ws-16-2",
        active_goal_status="ACTIVE",
        active_goal_progress=33.0,
        active_goal_completed_projects=1,
        active_goal_active_projects=1,
        active_goal_paused_projects=0,
        active_goal_total_projects=2,
        active_goal_last_activity="2026-07-27T18:00:00+00:00",
        active_goal_current_project="Proj",
        active_goal_current_mission="Mission",
        active_goal_last_summary="Earlier",
        active_goal_progress_updated_at="2026-07-27T18:00:00+00:00",
    )
    ctx = GoalContext.from_workspace(active)
    assert ctx is not None
    assert ctx.progress == 33.0
    assert ctx.completed_projects == 1
    assert ctx.total_projects == 2
    assert ctx.current_project == "Proj"
    assert ctx.current_mission == "Mission"
    assert ctx.last_activity == "2026-07-27T18:00:00+00:00"


def test_single_workspace_state_read_for_goal_progress(brain: Brain) -> None:
    """Goal progress/resume awareness must reuse the single WorkspaceState load."""
    goal = brain.goal_manager.create_goal("Perf Goal 16.2")
    project = brain.project_manager.create_project("Perf P", goal_id=goal.id)
    brain.mission_manager.create_mission(
        "Perf M",
        "x",
        ["s"],
        project_id=project.id,
    )

    load_calls = {"n": 0}
    original_load = brain.state_manager.load

    def tracking_load() -> WorkspaceState:
        load_calls["n"] += 1
        return original_load()

    brain.state_manager.load = tracking_load  # type: ignore[method-assign]
    brain.think("Compter les I/O goal")

    assert load_calls["n"] == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.goal_id == goal.id


def test_paused_projects_counted(tmp_path: Path) -> None:
    _state, goals, projects, _missions = _paired(tmp_path)
    goal = goals.create_goal("Counts")
    first = projects.create_project("A", goal_id=goal.id)
    second = projects.create_project("B", goal_id=goal.id)
    projects.pause_project(first.id)

    snapshot = goals.get_progress(goal.id)
    assert snapshot.paused_projects == 1
    assert snapshot.active_projects == 1
    assert snapshot.total_projects == 2
    assert second.status == ProjectState.ACTIVE.value

# =====================================
# Titan Project Manager Foundation Tests
# =====================================

"""Phase 15.1 ProjectManager / Project foundation tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from brain.brain import Brain
from brain.pipeline.context_bundle import ProjectContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.mission_manager import MissionManager
from core.project_manager import ProjectManager
from core.project_models import Project, ProjectPriority, ProjectState
from core.state_manager import StateManager, WorkspaceState


REQUIRED_PROJECT_FIELDS = {
    "id",
    "name",
    "description",
    "status",
    "created_at",
    "updated_at",
    "progress",
    "active_mission_id",
    "mission_ids",
    "priority",
}


def _assert_required_fields(project: Project | dict) -> None:
    payload = project.to_dict() if isinstance(project, Project) else project
    assert REQUIRED_PROJECT_FIELDS.issubset(payload.keys())


def _paired_managers(tmp_path: Path) -> tuple[StateManager, ProjectManager, MissionManager]:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    projects = ProjectManager(
        file_path=tmp_path / "titan_projects.json",
        state_manager=state,
    )
    missions = MissionManager(
        file_path=tmp_path / "titan_mission.json",
        state_manager=state,
        project_manager=projects,
    )
    return state, projects, missions


# ---------------------------------------------------------------------------
# Project creation
# ---------------------------------------------------------------------------


def test_create_project_returns_foundation_fields(tmp_path: Path) -> None:
    manager = ProjectManager(file_path=tmp_path / "titan_projects.json")
    project = manager.create_project(
        name="Titan OS",
        description="Personal agentic AI",
        priority=ProjectPriority.HIGH,
    )

    _assert_required_fields(project)
    assert project.name == "Titan OS"
    assert project.description == "Personal agentic AI"
    assert project.status == ProjectState.ACTIVE.value
    assert project.priority == ProjectPriority.HIGH
    assert project.progress == 0.0
    assert project.active_mission_id is None
    assert project.mission_ids == []
    assert manager.get_active_project() is not None
    assert manager.get_active_project().id == project.id


def test_project_persistence_round_trip(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_projects.json"
    manager = ProjectManager(file_path=file_path)
    created = manager.create_project("Persist Me", "Durable")

    reloaded = ProjectManager(file_path=file_path)
    loaded = reloaded.get_project(created.id)
    assert loaded is not None
    assert loaded.name == "Persist Me"
    assert loaded.description == "Durable"
    assert loaded.status == ProjectState.ACTIVE.value
    assert reloaded.get_active_project() is not None
    assert reloaded.get_active_project().id == created.id

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert created.id in on_disk["projects"]
    assert on_disk["active_project_id"] == created.id


def test_multiple_projects_single_active(tmp_path: Path) -> None:
    manager = ProjectManager(file_path=tmp_path / "titan_projects.json")
    first = manager.create_project("Alpha")
    second = manager.create_project("Beta")

    assert len(manager.list_projects()) == 2
    active = manager.get_active_project()
    assert active is not None
    assert active.id == second.id
    assert active.status == ProjectState.ACTIVE.value

    paused = manager.get_project(first.id)
    assert paused is not None
    assert paused.status == ProjectState.PAUSED.value


def test_active_project_switching(tmp_path: Path) -> None:
    manager = ProjectManager(file_path=tmp_path / "titan_projects.json")
    first = manager.create_project("Alpha")
    second = manager.create_project("Beta")

    resumed = manager.resume_project(first.id)
    assert resumed.status == ProjectState.ACTIVE.value
    assert manager.get_active_project().id == first.id

    other = manager.get_project(second.id)
    assert other is not None
    assert other.status == ProjectState.PAUSED.value


def test_pause_complete_archive_delete(tmp_path: Path) -> None:
    manager = ProjectManager(file_path=tmp_path / "titan_projects.json")
    created = manager.create_project("Lifecycle")

    paused = manager.pause_project(created.id)
    assert paused.status == ProjectState.PAUSED.value
    assert manager.get_active_project() is None

    resumed = manager.resume_project(created.id)
    assert resumed.status == ProjectState.ACTIVE.value

    completed = manager.complete_project(created.id)
    assert completed.status == ProjectState.COMPLETED.value
    assert completed.progress == 100.0
    assert manager.get_active_project() is None

    other = manager.create_project("Archive Target")
    archived = manager.archive_project(other.id)
    assert archived.status == ProjectState.ARCHIVED.value

    manager.delete_project(other.id)
    assert manager.get_project(other.id) is None


def test_workspace_state_mirrors_projects(tmp_path: Path) -> None:
    state, projects, _missions = _paired_managers(tmp_path)
    project = projects.create_project("Mirror Me", "Sync")

    snap = state.snapshot()
    assert snap.active_project_id == project.id
    assert snap.active_project == "Mirror Me"
    assert snap.active_project_status == ProjectState.ACTIVE.value
    assert snap.active_project_progress == 0.0
    assert isinstance(snap.projects, list)
    assert len(snap.projects) == 1
    assert snap.projects[0]["id"] == project.id
    assert snap.projects[0]["name"] == "Mirror Me"


# ---------------------------------------------------------------------------
# Mission ownership
# ---------------------------------------------------------------------------


def test_mission_belongs_to_project(tmp_path: Path) -> None:
    _state, projects, missions = _paired_managers(tmp_path)
    project = projects.create_project("Owner")

    mission = missions.create_mission(
        "Owned Mission",
        "Objective",
        ["A", "B"],
        project_id=project.id,
    )

    assert mission.project_id == project.id
    owned = projects.get_project(project.id)
    assert owned is not None
    assert mission.id in owned.mission_ids
    assert owned.active_mission_id == mission.id


def test_mission_defaults_to_active_project(tmp_path: Path) -> None:
    _state, projects, missions = _paired_managers(tmp_path)
    project = projects.create_project("Default Owner")

    mission = missions.create_mission("Auto Owned", "Obj", ["A"])
    assert mission.project_id == project.id


def test_mission_rejects_unknown_project(tmp_path: Path) -> None:
    _state, _projects, missions = _paired_managers(tmp_path)

    with pytest.raises(ValueError, match="Unknown project id"):
        missions.create_mission(
            "Orphan",
            "Obj",
            ["A"],
            project_id="does-not-exist",
        )


def test_mission_requires_project_when_manager_bound(tmp_path: Path) -> None:
    """Without an active project, MissionManager auto-creates a default owner."""
    _state, projects, missions = _paired_managers(tmp_path)
    projects.pause_project(projects.create_project("Temp").id)

    mission = missions.create_mission("Auto Default Owner", "Obj", ["A"])
    assert mission.project_id is not None
    owner = projects.get_project(mission.project_id)
    assert owner is not None
    assert owner.status == ProjectState.ACTIVE.value
    assert mission.id in owner.mission_ids


# ---------------------------------------------------------------------------
# Brain awareness
# ---------------------------------------------------------------------------


def test_brain_loads_active_project(brain: Brain) -> None:
    project = brain.project_manager.create_project(
        "Brain Project",
        "Phase 15.1",
    )
    brain.mission_manager.create_mission(
        "Brain Mission",
        "Ship it",
        ["Wire", "Test"],
        project_id=project.id,
    )

    brain.think("Quelle est le projet actif ?")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_project_id == project.id
    assert ctx.workspace_state.active_project == "Brain Project"
    assert ctx.project_context is not None
    assert ctx.project_context.name == "Brain Project"
    assert ctx.project_context.project_id == project.id
    assert ctx.mission_context is not None
    assert ctx.mission_context.active_mission == "Brain Mission"


def test_prompt_includes_project_and_mission_metadata() -> None:
    project_context = ProjectContext(
        name="Titan",
        status="ACTIVE",
        progress=25.0,
        project_id="proj-1",
    )
    from brain.pipeline.context_bundle import MissionContext

    mission_context = MissionContext(
        active_mission="Ship Phase 15.1",
        status="RUNNING",
        progress=40.0,
    )
    ctx = ThinkContext(
        user_message="Continue.",
        project_context=project_context,
        mission_context=mission_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONTEXTE PROJET" in prompt
    assert "Current Project:" in prompt
    assert "Titan" in prompt
    assert "Project Progress:" in prompt
    assert "25.0" in prompt
    assert "Current Mission:" in prompt
    assert "Last Completed Step:" in prompt
    assert "Current Objective:" in prompt
    assert "CONTEXTE MISSION" in prompt
    assert "Ship Phase 15.1" in prompt
    assert "Mission Progress:" in prompt
    assert "40.0" in prompt


def test_project_diagnostics_emitted(brain: Brain, caplog: Any) -> None:
    with caplog.at_level(logging.INFO):
        project = brain.project_manager.create_project("Diag Project")
        brain.think("Diagnostics projet")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PROJECT_CREATED") for msg in messages)
    assert any(msg.startswith("PROJECT_LOADED") for msg in messages)
    assert any(msg.startswith("PROJECT_CONTEXT_LOADED") for msg in messages)
    assert brain.last_think_context is not None
    assert brain.last_think_context.project_context is not None
    assert brain.last_think_context.project_context.project_id == project.id


def test_project_switched_and_completed_diagnostics(
    tmp_path: Path,
    caplog: Any,
) -> None:
    manager = ProjectManager(file_path=tmp_path / "titan_projects.json")
    first = manager.create_project("One")

    with caplog.at_level(logging.INFO):
        manager.create_project("Two")
        manager.complete_project(first.id)
        other = manager.list_projects(status=ProjectState.ACTIVE)[0]
        manager.archive_project(other.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PROJECT_SWITCHED") for msg in messages)
    assert any(msg.startswith("PROJECT_COMPLETED") for msg in messages)
    assert any(msg.startswith("PROJECT_ARCHIVED") for msg in messages)


def test_single_workspace_state_read_for_project_awareness(brain: Brain) -> None:
    """Project awareness must come from the one WorkspaceState load in _begin_think."""
    project = brain.project_manager.create_project("Perf Project")
    load_calls = {"count": 0}
    original_load = brain.state_manager.load

    def counting_load() -> WorkspaceState:
        load_calls["count"] += 1
        return original_load()

    brain.state_manager.load = counting_load  # type: ignore[method-assign]
    brain.think("Check project load count")

    assert load_calls["count"] == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert ctx.project_context.project_id == project.id

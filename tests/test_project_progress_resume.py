# =====================================
# Titan Project Progress & Resume Tests
# =====================================

"""Phase 15.2 — project progress persists and resumes across think cycles."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import ProjectContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.mission_manager import MissionManager
from core.project_manager import ProjectManager
from core.state_manager import StateManager, WorkspaceState


def _seed_active_project(brain: Brain, **overrides: Any) -> None:
    payload = {
        "active_project": "Progress Resume Project",
        "active_project_id": "project-15-2",
        "active_project_status": "ACTIVE",
        "active_project_progress": 25.0,
        "active_project_active_mission": "Wire progress",
        "active_project_completed_missions": ["Foundation"],
        "active_project_last_completed_step": "Scaffold",
        "active_project_last_summary": "Earlier project progress note",
        "active_project_progress_updated_at": "2026-01-01T00:00:00+00:00",
        "active_project_current_objective": "Wire progress",
        "projects": [
            {
                "id": "project-15-2",
                "name": "Progress Resume Project",
                "status": "ACTIVE",
                "progress": 25.0,
            }
        ],
    }
    payload.update(overrides)
    brain.state_manager.update(**payload)


def test_project_progress_persists_after_think(brain: Brain) -> None:
    """Successful think must stamp project resume fields onto WorkspaceState."""
    _seed_active_project(brain)

    brain.think("Continuer le travail en cours")

    snap = brain.state_manager.snapshot()
    assert snap.active_project_id == "project-15-2"
    assert snap.active_project == "Progress Resume Project"
    assert snap.active_project_progress == 25.0
    assert snap.active_project_last_completed_step == "Scaffold"
    assert snap.active_project_current_objective == "Wire progress"
    assert snap.active_project_last_summary
    assert "Réponse de test." in (snap.active_project_last_summary or "")
    assert snap.active_project_progress_updated_at is not None
    assert snap.active_project_progress_updated_at != "2026-01-01T00:00:00+00:00"
    assert snap.updated_at is not None

    on_disk = brain.state_manager.load()
    assert on_disk.active_project_last_summary == snap.active_project_last_summary
    assert on_disk.active_project_progress_updated_at == (
        snap.active_project_progress_updated_at
    )


def test_project_resume_survives_multiple_think_cycles(brain: Brain) -> None:
    """Resume fields from cycle N must load into ThinkContext on cycle N+1."""
    _seed_active_project(brain)

    brain.think("Premier cycle projet")
    first = brain.state_manager.snapshot()
    first_summary = first.active_project_last_summary
    first_updated = first.active_project_progress_updated_at
    assert first_summary
    assert first_updated

    brain.llm.ask.return_value = "Deuxième réponse projet."
    brain.think("Deuxième cycle projet")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert "CONTEXTE PROJET" in ctx.prompt
    assert "Current Project:" in ctx.prompt
    assert "Progress Resume Project" in ctx.prompt
    assert "Project Progress:" in ctx.prompt
    assert "25.0" in ctx.prompt
    assert "Current Mission:" in ctx.prompt
    assert "Wire progress" in ctx.prompt
    assert "Last Completed Step:" in ctx.prompt
    assert "Scaffold" in ctx.prompt
    assert "Current Objective:" in ctx.prompt

    snap = brain.state_manager.snapshot()
    assert snap.active_project_last_summary
    assert "Deuxième réponse" in (snap.active_project_last_summary or "")
    assert snap.active_project_progress_updated_at != first_updated


def test_project_survives_restart(tmp_path: Path, brain: Brain) -> None:
    """Project resume must reload from disk after StateManager restart."""
    _seed_active_project(brain)
    brain.think("Persister avant restart")

    snap = brain.state_manager.snapshot()
    assert snap.active_project_last_summary
    state_path = Path(brain.state_manager.file_path)

    reloaded = StateManager(file_path=state_path)
    loaded = reloaded.load()
    assert loaded.active_project_id == "project-15-2"
    assert loaded.active_project == "Progress Resume Project"
    assert loaded.active_project_progress == 25.0
    assert loaded.active_project_last_completed_step == "Scaffold"
    assert loaded.active_project_current_objective == "Wire progress"
    assert loaded.active_project_last_summary == snap.active_project_last_summary
    assert loaded.active_project_progress_updated_at == (
        snap.active_project_progress_updated_at
    )


def test_prompt_includes_project_resume() -> None:
    """PromptBuilder must attach project resume labels when a project is active."""
    project_context = ProjectContext(
        name="Ship Phase 15.2",
        status="ACTIVE",
        progress=50.0,
        project_id="proj-15-2",
        active_mission="Resume tests",
        last_completed_step="Awareness",
        last_summary="Awareness done",
        progress_updated_at="2026-07-27T12:00:00+00:00",
        current_objective="Resume tests",
    )
    ctx = ThinkContext(
        user_message="Continue.",
        project_context=project_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONTEXTE PROJET" in prompt
    assert "Current Project:" in prompt
    assert "Ship Phase 15.2" in prompt
    assert "Project Progress:" in prompt
    assert "50.0" in prompt
    assert "Current Mission:" in prompt
    assert "Resume tests" in prompt
    assert "Last Completed Step:" in prompt
    assert "Awareness" in prompt
    assert "Current Objective:" in prompt


def test_no_active_project_unchanged_prompt_behavior() -> None:
    """Without an active project, project resume section must not appear."""
    baseline = ThinkContext(user_message="Bonjour", state={}, mission={})
    without = ThinkContext(
        user_message="Bonjour",
        state={},
        mission={},
        project_context=None,
    )
    builder = PromptBuilder()
    assert builder.build(baseline) == builder.build(without)
    assert "CONTEXTE PROJET" not in builder.build(without)
    assert "Current Project:" not in builder.build(without)
    assert "Project Progress:" not in builder.build(without)


def test_brain_prompt_omits_project_resume_when_no_project(brain: Brain) -> None:
    """End-to-end: idle WorkspaceState leaves prompt without project section."""
    brain.state_manager.update(
        active_project=None,
        active_project_id=None,
        active_project_status=None,
        active_project_progress=None,
        active_project_active_mission=None,
        active_project_completed_missions=[],
        active_project_last_completed_step=None,
        active_project_last_summary=None,
        active_project_progress_updated_at=None,
        active_project_current_objective=None,
        projects=[],
    )

    brain.think("Simple hello")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is None
    assert "CONTEXTE PROJET" not in ctx.prompt
    assert "Current Project:" not in ctx.prompt


def test_project_progress_diagnostics_emitted(
    brain: Brain,
    caplog: Any,
) -> None:
    """PROJECT_PROGRESS_UPDATED / RESUME_LOADED / RESUME_INJECTED must fire."""
    _seed_active_project(brain)

    with caplog.at_level(logging.INFO):
        brain.think("Diagnostics progress projet")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PROJECT_PROGRESS_UPDATED") for msg in messages)
    assert any(msg.startswith("PROJECT_RESUME_LOADED") for msg in messages)
    assert any(msg.startswith("PROJECT_RESUME_INJECTED") for msg in messages)


def test_no_project_skips_progress_and_resume_logs(
    brain: Brain,
    caplog: Any,
) -> None:
    """Without an active project, progress/resume diagnostics must not fire."""
    brain.state_manager.update(
        active_project=None,
        active_project_id=None,
        active_project_status=None,
        active_project_progress=None,
        active_project_active_mission=None,
        active_project_completed_missions=[],
        active_project_last_completed_step=None,
        active_project_last_summary=None,
        active_project_progress_updated_at=None,
        active_project_current_objective=None,
        projects=[],
    )

    with caplog.at_level(logging.INFO):
        brain.think("Pas de projet")

    messages = [record.getMessage() for record in caplog.records]
    assert not any(msg.startswith("PROJECT_PROGRESS_UPDATED") for msg in messages)
    assert not any(msg.startswith("PROJECT_RESUME_LOADED") for msg in messages)
    assert not any(msg.startswith("PROJECT_RESUME_INJECTED") for msg in messages)


def test_progress_update_from_live_project(brain: Brain) -> None:
    """Paired ProjectManager + MissionManager + think must mirror resume fields."""
    projects = brain.project_manager
    missions = brain.mission_manager
    projects.bind_state_manager(brain.state_manager)
    missions.bind_state_manager(brain.state_manager)
    missions.bind_project_manager(projects)

    project = projects.create_project("Live Progress Project", "Prove live resume")
    mission = missions.create_mission(
        title="Live Progress Mission",
        objective="Prove live resume",
        steps=["Alpha", "Beta", "Gamma"],
        project_id=project.id,
    )
    missions.complete_current_step()

    brain.think("Avance le projet")

    snap = brain.state_manager.snapshot()
    assert snap.active_project_id == project.id
    assert snap.active_project == "Live Progress Project"
    assert snap.active_project_active_mission == mission.title
    assert snap.active_project_last_completed_step == "Alpha"
    assert snap.active_project_current_objective == "Beta"
    assert abs(float(snap.active_project_progress or 0) - (100.0 / 3.0)) < 0.1
    assert snap.active_project_last_summary
    assert snap.active_project_progress_updated_at is not None

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert ctx.project_context.last_completed_step == "Alpha"
    assert ctx.project_context.current_objective == "Beta"
    assert ctx.project_context.active_mission == mission.title


def test_completed_missions_recorded_on_project(tmp_path: Path) -> None:
    """Completing a mission must append it to the project's completed list."""
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

    project = projects.create_project("Done Tracking")
    mission = missions.create_mission(
        "Finish Me",
        "Complete tracking",
        ["One"],
        project_id=project.id,
    )
    missions.complete_mission(mission.id)

    reloaded = projects.get_project(project.id)
    assert reloaded is not None
    assert mission.id in reloaded.completed_mission_ids
    assert reloaded.active_mission_id is None

    snap = state.snapshot()
    assert "Finish Me" in snap.active_project_completed_missions


def test_project_context_resume_from_workspace() -> None:
    """ProjectContext.from_workspace must expose Phase 15.2 resume fields."""
    active = WorkspaceState(
        active_project="From State",
        active_project_id="ws-15-2",
        active_project_status="ACTIVE",
        active_project_progress=40.0,
        active_project_active_mission="Second",
        active_project_completed_missions=["First"],
        active_project_last_completed_step="First step",
        active_project_last_summary="First done",
        active_project_progress_updated_at="2026-07-27T18:00:00+00:00",
        active_project_current_objective="Second",
    )
    ctx = ProjectContext.from_workspace(active)
    assert ctx is not None
    assert ctx.active_mission == "Second"
    assert ctx.completed_missions == ("First",)
    assert ctx.last_completed_step == "First step"
    assert ctx.last_summary == "First done"
    assert ctx.current_objective == "Second"
    assert ctx.progress_updated_at == "2026-07-27T18:00:00+00:00"


def test_single_state_read_write_for_project_progress(brain: Brain) -> None:
    """Project progress/resume must reuse the existing load/save pair."""
    _seed_active_project(brain)
    load_calls = {"n": 0}
    update_calls = {"n": 0}
    original_load = brain.state_manager.load
    original_update = brain.state_manager.update

    def tracking_load() -> WorkspaceState:
        load_calls["n"] += 1
        return original_load()

    def tracking_update(*args: Any, **kwargs: Any) -> WorkspaceState:
        update_calls["n"] += 1
        return original_update(*args, **kwargs)

    brain.state_manager.load = tracking_load  # type: ignore[method-assign]
    brain.state_manager.update = tracking_update  # type: ignore[method-assign]

    brain.think("Compter les I/O projet")

    assert load_calls["n"] == 1
    assert update_calls["n"] == 1

# =====================================
# Titan Multi-Mission Workspace Tests
# =====================================

"""Phase 14.5 — multiple missions, single ACTIVE focus, WorkspaceState mirror."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from brain.brain import Brain
from brain.pipeline.context_bundle import MissionContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.mission_manager import MissionManager
from core.mission_models import MissionState
from core.state_manager import StateManager


def _paired_managers(tmp_path: Path) -> tuple[MissionManager, StateManager]:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    missions = MissionManager(
        file_path=tmp_path / "titan_mission.json",
        state_manager=state,
    )
    return missions, state


# ---------------------------------------------------------------------------
# Persistence / multi-mission
# ---------------------------------------------------------------------------


def test_multiple_missions_persist(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    missions, state = _paired_managers(tmp_path)

    first = missions.create_mission("Alpha", "Obj A", ["A1", "A2"])
    second = missions.create_mission("Beta", "Obj B", ["B1"])
    third = missions.create_mission("Gamma", "Obj C", ["C1"])

    listed = missions.list_missions()
    assert {item.id for item in listed} == {first.id, second.id, third.id}

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert set(on_disk["missions"].keys()) == {first.id, second.id, third.id}
    assert on_disk["active_mission_id"] == third.id

    snap = state.snapshot()
    assert len(snap.missions) == 3
    assert snap.active_mission_id == third.id
    assert snap.mission_queue_count == 2


def test_active_mission_switching(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    first = missions.create_mission("One", "First", ["A"])
    second = missions.create_mission("Two", "Second", ["X", "Y"])

    assert missions.get_active_mission().id == second.id
    queued = missions.runtime.get_mission(first.id)
    assert queued is not None
    assert queued.state == MissionState.QUEUED
    assert state.snapshot().mission_queue_count == 1

    resumed = missions.resume_mission(first.id)
    assert resumed.id == first.id
    assert resumed.state == MissionState.RUNNING
    assert missions.get_active_mission().id == first.id

    demoted = missions.runtime.get_mission(second.id)
    assert demoted is not None
    assert demoted.state == MissionState.QUEUED

    snap = state.snapshot()
    assert snap.active_mission_id == first.id
    assert snap.active_mission_title == "One"
    assert snap.mission_queue_count == 1


def test_pause_and_resume_mission(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Pause Me", "Obj", ["A", "B"])

    paused = missions.pause_mission(created.id)
    assert paused.state == MissionState.PAUSED
    assert missions.get_active_mission() is None

    snap = state.snapshot()
    assert snap.active_mission_id is None
    assert snap.paused_mission_count == 1
    assert snap.mission_queue_count == 0

    resumed = missions.resume_mission(created.id)
    assert resumed.state == MissionState.RUNNING
    assert missions.get_active_mission().id == created.id
    assert state.snapshot().paused_mission_count == 0
    assert state.snapshot().active_mission_id == created.id


def test_complete_mission_clears_active_focus(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Finish Me", "Obj", ["A", "B"])

    completed = missions.complete_mission(created.id)
    assert completed.state == MissionState.COMPLETED
    assert missions.get_active_mission() is None
    assert state.snapshot().active_mission_id is None

    statuses = {item["id"]: item["status"] for item in state.snapshot().missions}
    assert statuses[created.id] == MissionState.COMPLETED.value


def test_archive_mission_retained_in_workspace_list(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Archive Me", "Obj", ["A"])

    archived = missions.archive_mission(created.id)
    assert archived.state == MissionState.ARCHIVED
    assert missions.get_active_mission() is None

    listed = missions.list_missions(include_archived=True)
    assert any(item.id == created.id for item in listed)
    snap = state.snapshot()
    assert any(
        entry["id"] == created.id and entry["status"] == MissionState.ARCHIVED.value
        for entry in snap.missions
    )


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_workspace_lifecycle_diagnostics(
    tmp_path: Path,
    caplog,
) -> None:
    missions, _state = _paired_managers(tmp_path)

    with caplog.at_level(logging.INFO):
        first = missions.create_mission("Diag One", "Obj", ["A"])
        second = missions.create_mission("Diag Two", "Obj", ["B"])
        missions.pause_mission(second.id)
        missions.resume_mission(first.id)
        missions.complete_mission(first.id)
        missions.archive_mission(second.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any("MISSION_CREATED" in msg for msg in messages)
    assert any("MISSION_SWITCHED" in msg for msg in messages)
    assert any("MISSION_PAUSED" in msg for msg in messages)
    assert any("MISSION_RESUMED" in msg for msg in messages)
    assert any("MISSION_COMPLETED" in msg for msg in messages)
    assert any("MISSION_ARCHIVED" in msg for msg in messages)


# ---------------------------------------------------------------------------
# Brain — only active mission in prompt / context
# ---------------------------------------------------------------------------


def test_brain_receives_only_active_mission(brain: Brain) -> None:
    """Brain.think uses WorkspaceState active slice — never other mission bodies."""
    first = brain.create_mission("Workspace Alpha", "Obj A", ["A1"])
    second = brain.create_mission("Workspace Beta", "Obj B", ["B1", "B2"])

    assert brain.mission_manager.get_active_mission().id == second.id
    queued = brain.mission_manager.runtime.get_mission(first.id)
    assert queued is not None
    assert queued.state == MissionState.QUEUED

    brain.think("Continue the active mission only")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.mission_context is not None
    assert ctx.mission_context.has_active_mission
    assert ctx.mission_context.active_mission == "Workspace Beta"
    assert ctx.mission_context.queue_count == 1
    assert ctx.mission_context.paused_count == 0

    # Legacy flat mission view is the active focus only.
    assert ctx.mission.get("title") == "Workspace Beta"
    assert "Workspace Alpha" not in (ctx.mission.get("title") or "")

    prompt = ctx.prompt
    assert "Active Mission:" in prompt
    assert "Workspace Beta" in prompt
    assert "Mission Queue Count:" in prompt
    assert "Paused Mission Count:" in prompt
    # Full multi-mission map must not appear under MISSION ACTIVE.
    mission_section = prompt.split("MISSION ACTIVE", 1)[1].split(
        "=========================================", 1
    )[0]
    assert '"missions"' not in mission_section or '"missions": {}' in mission_section
    assert "Workspace Alpha" not in mission_section
    assert "Obj A" not in mission_section


def test_prompt_builder_includes_workspace_counts_only() -> None:
    mission_context = MissionContext(
        active_mission="Ship Phase 14.5",
        status="RUNNING",
        progress=0.25,
        priority="HIGH",
        stage="Tests",
        queue_count=2,
        paused_count=1,
    )
    ctx = ThinkContext(
        user_message="Continue.",
        mission_context=mission_context,
        state={},
        mission={"active": True, "title": "Ship Phase 14.5"},
    )
    prompt = PromptBuilder().build(ctx)

    assert "Active Mission:" in prompt
    assert "Ship Phase 14.5" in prompt
    assert "Mission Queue Count:\n2" in prompt
    assert "Paused Mission Count:\n1" in prompt


def test_single_workspace_state_read_for_mission_context(brain: Brain) -> None:
    """Mission awareness comes from the one WorkspaceState load in _begin_think."""
    brain.create_mission("Focus", "Obj", ["Step"])
    brain.pause_mission()
    other = brain.create_mission("Live", "Obj", ["Step"])

    brain.think("Single read check")
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_mission_id == other.id
    assert ctx.mission_context is not None
    assert ctx.mission_context.active_mission == "Live"
    assert ctx.mission_context.paused_count == 1
    assert ctx.mission_context.queue_count == 0

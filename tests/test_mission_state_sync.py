# =====================================
# Titan Mission ↔ WorkspaceState Sync Tests
# =====================================

"""Phase 14.2 — MissionManager keeps WorkspaceState active-mission fields in sync."""

from __future__ import annotations

import logging
from pathlib import Path

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


def _assert_mirror(
    state: StateManager,
    *,
    mission_id: str | None,
    title: str | None,
    status: str | None,
    progress: float | None,
    priority: str | None = None,
    stage: str | None = None,
) -> None:
    snap = state.snapshot()
    assert snap.active_mission_id == mission_id
    assert snap.active_mission_title == title
    assert snap.active_mission_status == status
    assert snap.active_mission_progress == progress
    assert snap.active_mission == title
    if mission_id is None:
        assert snap.active_mission_priority is None
        assert snap.active_mission_stage is None
    else:
        if priority is not None:
            assert snap.active_mission_priority == priority
        if stage is not None:
            assert snap.active_mission_stage == stage


def test_mission_creation_updates_workspace_state(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)

    mission = missions.create_mission(
        title="Sync Create",
        objective="Prove create mirrors state",
        steps=["A", "B"],
    )

    _assert_mirror(
        state,
        mission_id=mission.id,
        title="Sync Create",
        status=MissionState.READY.value,
        progress=0.0,
        priority="NORMAL",
        stage="A",
    )
    on_disk = state.load()
    assert on_disk.active_mission_id == mission.id
    assert on_disk.active_mission_title == "Sync Create"


def test_mission_completion_updates_workspace_state(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Sync Complete", "Obj", ["A", "B"])

    missions.complete_mission(created.id)

    _assert_mirror(
        state,
        mission_id=None,
        title=None,
        status=None,
        progress=None,
    )
    assert missions.get_active_mission() is None


def test_mission_cancellation_updates_workspace_state(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Sync Cancel", "Obj", ["A"])

    missions.cancel_mission(created.id)

    _assert_mirror(
        state,
        mission_id=None,
        title=None,
        status=None,
        progress=None,
    )
    assert missions.get_active_mission() is None


def test_mission_switching_updates_workspace_state(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    first = missions.create_mission("Mission One", "First", ["A"])
    second = missions.create_mission("Mission Two", "Second", ["X", "Y"])

    _assert_mirror(
        state,
        mission_id=second.id,
        title="Mission Two",
        status=MissionState.READY.value,
        progress=0.0,
    )

    resumed = missions.resume_mission(first.id)

    assert resumed.id == first.id
    _assert_mirror(
        state,
        mission_id=first.id,
        title="Mission One",
        status=MissionState.RUNNING.value,
        progress=0.0,
    )


def test_mission_update_and_archive_sync_workspace_state(tmp_path: Path) -> None:
    missions, state = _paired_managers(tmp_path)
    created = missions.create_mission("Sync Update", "Obj", ["A", "B"])

    updated = missions.update_mission(
        created.id,
        title="Renamed Mission",
        progress=50.0,
    )
    _assert_mirror(
        state,
        mission_id=updated.id,
        title="Renamed Mission",
        status=updated.status,
        progress=50.0,
    )

    missions.archive_mission(updated.id)
    _assert_mirror(
        state,
        mission_id=None,
        title=None,
        status=None,
        progress=None,
    )


def test_mission_sync_emits_diagnostic_logs(
    tmp_path: Path,
    caplog,
) -> None:
    missions, state = _paired_managers(tmp_path)

    with caplog.at_level(logging.INFO, logger="core.mission_manager"):
        created = missions.create_mission("Log Me", "Obj", ["A"])
        missions.complete_mission(created.id)

    messages = [record.getMessage() for record in caplog.records]
    assert any("MISSION_SYNC_BEGIN" in msg for msg in messages)
    assert any("MISSION_SYNC_DONE" in msg for msg in messages)
    assert any("MISSION_ACTIVE_CHANGED" in msg for msg in messages)

    # Final mirror remains cleared after completion.
    _assert_mirror(
        state,
        mission_id=None,
        title=None,
        status=None,
        progress=None,
    )


def test_mission_manager_without_state_manager_still_works(tmp_path: Path) -> None:
    """Sync is optional — MissionManager remains usable standalone."""
    missions = MissionManager(file_path=tmp_path / "titan_mission.json")
    mission = missions.create_mission("Standalone", "Obj", ["A"])
    assert mission.id is not None
    assert missions.get_active_mission().id == mission.id

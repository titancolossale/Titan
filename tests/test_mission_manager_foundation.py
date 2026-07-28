# =====================================
# Titan Mission Manager Foundation Tests
# =====================================

"""Phase 14.1 MissionManager / Mission foundation tests."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from core.mission_manager import MissionManager
from core.mission_migrator import SCHEMA_VERSION
from core.mission_models import Mission, MissionPriority, MissionState


REQUIRED_MISSION_FIELDS = {
    "id",
    "title",
    "description",
    "status",
    "priority",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "progress",
    "tags",
    "parent_mission",
    "child_missions",
    "current_step",
    "next_step",
    "notes",
    "project_id",
}


def _assert_required_fields(mission: Mission | dict) -> None:
    payload = mission.to_dict() if isinstance(mission, Mission) else mission
    assert REQUIRED_MISSION_FIELDS.issubset(payload.keys())


# ---------------------------------------------------------------------------
# Mission creation
# ---------------------------------------------------------------------------


def test_create_mission_returns_foundation_fields(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    mission = manager.create_mission(
        title="Build Mission Manager",
        objective="Ship Phase 14.1",
        steps=["Model", "API", "Tests"],
        tags=["foundation", "core"],
        notes="Owned exclusively by MissionManager",
    )

    _assert_required_fields(mission)
    assert mission.title == "Build Mission Manager"
    assert mission.description == "Ship Phase 14.1"
    assert mission.objective == "Ship Phase 14.1"
    assert mission.status == MissionState.READY.value
    assert mission.priority == MissionPriority.NORMAL
    assert mission.progress == 0.0
    assert mission.tags == ["foundation", "core"]
    assert mission.notes == "Owned exclusively by MissionManager"
    assert mission.current_step == "Model"
    assert mission.next_step == "API"
    assert mission.parent_mission is None
    assert mission.child_missions == []
    assert mission.started_at is None
    assert mission.completed_at is None
    assert manager.get_active_mission() is not None
    assert manager.get_active_mission().id == mission.id


def test_create_mission_with_description_alias(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    mission = manager.create_mission(
        title="Alias Test",
        steps=["A"],
        description="Primary description",
    )
    assert mission.description == "Primary description"
    assert mission.objective == "Primary description"


# ---------------------------------------------------------------------------
# Mission update
# ---------------------------------------------------------------------------


def test_update_mission_fields_and_persist(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    created = manager.create_mission("Update Me", "Original", ["A", "B"])

    updated = manager.update_mission(
        created.id,
        title="Updated Title",
        description="Updated description",
        tags=["alpha"],
        notes="note-1",
        priority=MissionPriority.HIGH,
        status=MissionState.RUNNING,
    )

    assert updated.title == "Updated Title"
    assert updated.description == "Updated description"
    assert updated.objective == "Updated description"
    assert updated.tags == ["alpha"]
    assert updated.notes == "note-1"
    assert updated.priority == MissionPriority.HIGH
    assert updated.status == MissionState.RUNNING.value
    assert updated.started_at is not None

    reloaded = MissionManager(file_path=file_path)
    loaded = reloaded.runtime.get_mission(created.id)
    assert loaded is not None
    assert loaded.title == "Updated Title"
    assert loaded.tags == ["alpha"]
    assert loaded.status == MissionState.RUNNING.value


# ---------------------------------------------------------------------------
# Mission completion / cancellation / archive / delete
# ---------------------------------------------------------------------------


def test_complete_mission_stamps_progress_and_completed_at(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Complete Me", "Obj", ["A", "B"])

    completed = manager.complete_mission(created.id)

    assert completed.status == MissionState.COMPLETED.value
    assert completed.progress == 100.0
    assert completed.completed_at is not None
    assert completed.current_step is None
    assert completed.next_step is None
    assert manager.get_active_mission() is None


def test_cancel_mission_marks_cancelled(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Cancel Me", "Obj", ["A"])

    cancelled = manager.cancel_mission(created.id)

    assert cancelled is not None
    assert cancelled.status == MissionState.CANCELLED.value
    assert cancelled.completed_at is not None
    assert manager.get_active_mission() is None


def test_archive_mission_retains_record(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Archive Me", "Obj", ["A"])

    archived = manager.archive_mission(created.id)

    assert archived.status == MissionState.ARCHIVED.value
    listed = manager.list_missions(include_archived=True)
    assert any(item.id == created.id for item in listed)
    assert manager.list_missions(include_archived=False) == []


def test_delete_mission_removes_from_persistence(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    created = manager.create_mission("Delete Me", "Obj", ["A"])

    manager.delete_mission(created.id)

    assert manager.runtime.get_mission(created.id) is None
    assert manager.list_missions() == []
    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert created.id not in on_disk["missions"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_mission_persistence_round_trip(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    created = manager.create_mission(
        title="Persist Me",
        objective="Round trip",
        steps=["One", "Two"],
        tags=["persist"],
        notes="keep me",
    )

    reloaded = MissionManager(file_path=file_path)
    loaded = reloaded.runtime.get_mission(created.id)
    assert loaded is not None
    _assert_required_fields(loaded)
    assert loaded.title == "Persist Me"
    assert loaded.description == "Round trip"
    assert loaded.tags == ["persist"]
    assert loaded.notes == "keep me"
    assert loaded.current_step == "One"
    assert loaded.next_step == "Two"

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SCHEMA_VERSION
    assert "Avancer" not in file_path.read_text(encoding="utf-8")


def test_mission_persistence_keeps_unicode(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    manager.create_mission(
        title="Mission française",
        objective="Avancer concrètement",
        steps=["Étape 1"],
    )
    raw = file_path.read_text(encoding="utf-8")
    assert "Avancer concrètement" in raw
    assert "\\u" not in raw


def test_missing_file_does_not_write_on_load(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    assert manager.get_active_mission() is None
    assert manager.list_missions() == []
    assert not file_path.exists()


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------


def test_mission_hierarchy_parent_child_links(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    parent = manager.create_mission("Parent", "Parent obj", ["P1"])
    child = manager.create_mission(
        "Child",
        "Child obj",
        ["C1"],
        parent_mission=parent.id,
    )

    parent_reloaded = manager.runtime.get_mission(parent.id)
    child_reloaded = manager.runtime.get_mission(child.id)
    assert parent_reloaded is not None
    assert child_reloaded is not None
    assert child_reloaded.parent_mission == parent.id
    assert parent_reloaded.child_missions == [child.id]

    manager.delete_mission(child.id)
    parent_after = manager.runtime.get_mission(parent.id)
    assert parent_after is not None
    assert parent_after.child_missions == []


def test_delete_parent_detaches_children(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    parent = manager.create_mission("Parent", "Obj", ["P1"])
    child = manager.create_mission(
        "Child",
        "Obj",
        ["C1"],
        parent_mission=parent.id,
    )

    manager.delete_mission(parent.id)

    orphan = manager.runtime.get_mission(child.id)
    assert orphan is not None
    assert orphan.parent_mission is None


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def test_mission_progress_advances_with_steps(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Progress", "Obj", ["A", "B", "C"])
    assert created.progress == 0.0
    assert created.next_step == "B"

    manager.complete_current_step()
    active = manager.get_active_mission()
    assert active is not None
    assert active.current_step == "B"
    assert active.next_step == "C"
    assert active.progress == pytest.approx(33.33, abs=0.1)

    manager.complete_current_step()
    active = manager.get_active_mission()
    assert active is not None
    assert active.current_step == "C"
    assert active.next_step is None
    assert active.progress == pytest.approx(66.67, abs=0.1)

    manager.complete_current_step()
    assert manager.get_active_mission() is None
    focused = manager.runtime.get_focused_mission()
    assert focused is not None
    assert focused.progress == 100.0
    assert focused.status == MissionState.COMPLETED.value


def test_update_mission_progress_override(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Progress Override", "Obj", ["A", "B"])
    updated = manager.update_mission(created.id, progress=42.5)
    assert updated.progress == 42.5
    assert updated.progress_percent == 42.5


# ---------------------------------------------------------------------------
# List missions
# ---------------------------------------------------------------------------


def test_list_missions_includes_all_statuses(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    first = manager.create_mission("One", "Obj", ["A"])
    second = manager.create_mission("Two", "Obj", ["B"])
    manager.complete_mission(first.id)

    all_missions = manager.list_missions()
    assert {item.id for item in all_missions} == {first.id, second.id}

    active = manager.list_missions(active_only=True)
    assert [item.id for item in active] == [second.id]

    completed = manager.list_missions(status=MissionState.COMPLETED)
    assert [item.id for item in completed] == [first.id]


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_concurrent_mission_updates_are_thread_safe(tmp_path: Path) -> None:
    file_path = tmp_path / "titan_mission.json"
    manager = MissionManager(file_path=file_path)
    created = manager.create_mission("Concurrent", "Obj", ["A", "B", "C"])
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            manager.update_mission(
                created.id,
                notes=f"note-{index}",
                tags=[f"tag-{index}"],
            )
            manager.list_missions()
            manager.get_active_mission()
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert errors == []
    loaded = manager.runtime.get_mission(created.id)
    assert loaded is not None
    _assert_required_fields(loaded)
    assert isinstance(loaded.tags, list)
    assert len(loaded.tags) == 1
    assert loaded.notes.startswith("note-")

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert isinstance(on_disk, dict)
    assert created.id in on_disk["missions"]
    _assert_required_fields(on_disk["missions"][created.id])


def test_concurrent_readers_see_consistent_copies(tmp_path: Path) -> None:
    manager = MissionManager(file_path=tmp_path / "titan_mission.json")
    created = manager.create_mission("Stable", "Obj", ["A", "B"])

    def reader(_: int) -> dict:
        active = manager.get_active_mission()
        assert active is not None
        listed = manager.list_missions()
        assert any(item.id == created.id for item in listed)
        return active.to_dict()

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(reader, i) for i in range(40)]
        for future in as_completed(futures):
            result = future.result(timeout=5)
            assert result["title"] == "Stable"
            _assert_required_fields(result)

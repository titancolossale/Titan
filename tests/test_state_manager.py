# =====================================
# Titan StateManager Tests
# =====================================

"""Unit tests for Phase 13.1 StateManager / WorkspaceState foundation."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.state_manager import SCHEMA_VERSION, StateManager, WorkspaceState, default_schema


def _assert_required_fields(state: WorkspaceState | dict) -> None:
    required = {
        "active_project",
        "active_project_id",
        "active_project_status",
        "active_project_progress",
        "projects",
        "active_project_active_mission",
        "active_project_completed_missions",
        "active_project_last_completed_step",
        "active_project_last_summary",
        "active_project_progress_updated_at",
        "active_project_current_objective",
        "active_mission",
        "active_mission_id",
        "active_mission_title",
        "active_mission_status",
        "active_mission_progress",
        "active_mission_priority",
        "active_mission_stage",
        "active_mission_last_completed_step",
        "active_mission_last_summary",
        "active_mission_progress_updated_at",
        "active_mission_current_objective",
        "missions",
        "mission_queue_count",
        "paused_mission_count",
        "current_step",
        "current_goal",
        "next_action",
        "current_focus",
        "running_tasks",
        "active_tools",
        "important_decisions",
        "brain_mode",
        "progress",
        "conversation_state",
        "current_execution_risk",
        "confirmation_pending",
        "confirmation_id",
        "blocked_reason",
        "updated_at",
    }
    if isinstance(state, WorkspaceState):
        payload = state.to_dict()
    else:
        payload = state
    assert required.issubset(payload.keys())


# ---------------------------------------------------------------------------
# State creation
# ---------------------------------------------------------------------------


def test_workspace_state_default_creation() -> None:
    """WorkspaceState defaults must include the Phase 13.1 field set."""
    state = WorkspaceState()
    _assert_required_fields(state)
    assert state.active_project == "Titan"
    assert state.active_mission is None
    assert state.active_mission_id is None
    assert state.active_mission_title is None
    assert state.active_mission_status is None
    assert state.active_mission_progress is None
    assert state.active_mission_priority is None
    assert state.active_mission_stage is None
    assert state.active_mission_last_completed_step is None
    assert state.active_mission_last_summary is None
    assert state.active_mission_progress_updated_at is None
    assert state.active_mission_current_objective is None
    assert state.active_project_id is None
    assert state.active_project_status is None
    assert state.active_project_progress is None
    assert state.projects == []
    assert state.active_project_active_mission is None
    assert state.active_project_completed_missions == []
    assert state.active_project_last_completed_step is None
    assert state.active_project_last_summary is None
    assert state.active_project_progress_updated_at is None
    assert state.active_project_current_objective is None
    assert state.missions == []
    assert state.mission_queue_count == 0
    assert state.paused_mission_count == 0
    assert state.current_step == "Développement du State Manager"
    assert state.current_goal is None
    assert state.next_action == "Connecter le State Manager au Brain"
    assert state.current_focus is None
    assert state.running_tasks == []
    assert state.active_tools == []
    assert state.important_decisions == []
    assert state.brain_mode == "idle"
    assert state.progress == "En développement"
    assert state.conversation_state == {
        "last_user_message": None,
        "last_titan_response": None,
    }
    assert state.updated_at is None
    assert state.to_dict()["schema_version"] == SCHEMA_VERSION


def test_default_schema_matches_workspace_state() -> None:
    """default_schema() must mirror a fresh WorkspaceState document."""
    schema = default_schema()
    _assert_required_fields(schema)
    assert schema == WorkspaceState().to_dict()


def test_state_manager_creates_workspace_state_in_memory(
    tmp_path: Path,
) -> None:
    """StateManager must own one WorkspaceState without writing on first load."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)

    snap = manager.snapshot()
    assert isinstance(snap, WorkspaceState)
    _assert_required_fields(snap)
    assert not file_path.exists()


# ---------------------------------------------------------------------------
# State loading
# ---------------------------------------------------------------------------


def test_load_returns_default_schema_when_file_missing(tmp_path: Path) -> None:
    """Missing JSON file must yield defaults without writing to disk."""
    file_path = tmp_path / "titan_state.json"
    assert not file_path.exists()

    manager = StateManager(file_path=file_path)
    loaded = manager.load()

    assert isinstance(loaded, WorkspaceState)
    assert loaded.active_project == "Titan"
    assert loaded.progress == "En développement"
    assert not file_path.exists()


def test_load_migrates_legacy_flat_message_keys(tmp_path: Path) -> None:
    """Legacy titan_state.json keys must migrate into conversation_state."""
    file_path = tmp_path / "titan_state.json"
    file_path.write_text(
        json.dumps(
            {
                "active_project": "Titan",
                "current_step": "Legacy step",
                "last_user_message": "Bonjour",
                "last_titan_response": "Salut",
                "next_action": "Continue",
                "progress": "Legacy",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = StateManager(file_path=file_path)
    snap = manager.snapshot()

    assert snap.conversation_state["last_user_message"] == "Bonjour"
    assert snap.conversation_state["last_titan_response"] == "Salut"
    assert manager.get_state()["last_user_message"] == "Bonjour"
    assert manager.get_state()["last_titan_response"] == "Salut"
    assert snap.current_step == "Legacy step"


# ---------------------------------------------------------------------------
# State updating
# ---------------------------------------------------------------------------


def test_update_replaces_fields_and_persists(tmp_path: Path) -> None:
    """update() must replace provided fields, stamp updated_at, and persist."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)

    result = manager.update(
        active_project="Titan V2",
        current_goal="Ship State Manager",
        brain_mode="planning",
        running_tasks=["implement", "test"],
    )

    assert result.active_project == "Titan V2"
    assert result.current_goal == "Ship State Manager"
    assert result.brain_mode == "planning"
    assert result.running_tasks == ["implement", "test"]
    assert result.updated_at is not None
    assert file_path.exists()

    reloaded = StateManager(file_path=file_path)
    assert reloaded.snapshot().active_project == "Titan V2"
    assert reloaded.snapshot().running_tasks == ["implement", "test"]


def test_update_state_legacy_single_key(tmp_path: Path) -> None:
    """Legacy update_state(key, value) must route through update()."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)

    manager.update_state("active_project", "Titan V2")
    manager.update_state("progress", "Phase 13.1")

    reloaded = StateManager(file_path=file_path)
    assert reloaded.get_state()["active_project"] == "Titan V2"
    assert reloaded.get_state()["progress"] == "Phase 13.1"


def test_update_after_response_persists_last_messages(
    state_manager: StateManager,
    tmp_path: Path,
) -> None:
    """update_after_response must set last messages and persist them to JSON."""
    state_manager.update_after_response(
        "Comment ça marche ?",
        "Voici comment ça fonctionne.",
    )

    assert state_manager.get_state()["last_user_message"] == "Comment ça marche ?"
    assert state_manager.get_state()["last_titan_response"] == (
        "Voici comment ça fonctionne."
    )
    assert state_manager.snapshot().conversation_state["last_user_message"] == (
        "Comment ça marche ?"
    )

    reloaded = StateManager(file_path=tmp_path / "titan_state.json")
    assert reloaded.get_state()["last_user_message"] == "Comment ça marche ?"
    assert reloaded.get_state()["last_titan_response"] == (
        "Voici comment ça fonctionne."
    )


def test_get_state_mutations_do_not_affect_live_state(tmp_path: Path) -> None:
    """External mutation of get_state()/snapshot() must not alter live state."""
    manager = StateManager(file_path=tmp_path / "titan_state.json")
    view = manager.get_state()
    view["active_project"] = "Hacked"
    view["running_tasks"].append("injected")
    view["conversation_state"]["last_user_message"] = "injected"

    snap = manager.snapshot()
    snap.active_project = "Also hacked"
    snap.running_tasks.append("also-injected")

    live = manager.snapshot()
    assert live.active_project == "Titan"
    assert live.running_tasks == []
    assert live.conversation_state["last_user_message"] is None


# ---------------------------------------------------------------------------
# State merge
# ---------------------------------------------------------------------------


def test_merge_combines_partial_patch(tmp_path: Path) -> None:
    """merge() must overwrite provided scalars and merge conversation_state."""
    manager = StateManager(file_path=tmp_path / "titan_state.json")
    manager.update(
        active_project="Alpha",
        current_focus="State Manager",
        important_decisions=["keep JSON persistence"],
        conversation_state={"last_user_message": "hi", "topic": "state"},
    )

    merged = manager.merge(
        {
            "current_goal": "Complete Phase 13.1",
            "active_tools": ["state_manager"],
            "conversation_state": {"last_titan_response": "ack"},
        }
    )

    assert merged.active_project == "Alpha"
    assert merged.current_focus == "State Manager"
    assert merged.current_goal == "Complete Phase 13.1"
    assert merged.active_tools == ["state_manager"]
    assert merged.important_decisions == ["keep JSON persistence"]
    assert merged.conversation_state["last_user_message"] == "hi"
    assert merged.conversation_state["last_titan_response"] == "ack"
    assert merged.conversation_state["topic"] == "state"
    assert merged.updated_at is not None


def test_merge_accepts_workspace_state_instance(tmp_path: Path) -> None:
    """merge() must accept a WorkspaceState patch and apply non-default fields."""
    manager = StateManager(file_path=tmp_path / "titan_state.json")
    manager.update(active_project="Keep Me", progress="in progress")
    patch = WorkspaceState(
        active_mission="Build foundation",
        next_action="Write tests",
        brain_mode="executing",
    )

    merged = manager.merge(patch)
    assert merged.active_mission == "Build foundation"
    assert merged.next_action == "Write tests"
    assert merged.brain_mode == "executing"
    assert merged.active_project == "Keep Me"
    assert merged.progress == "in progress"


# ---------------------------------------------------------------------------
# State reset
# ---------------------------------------------------------------------------


def test_reset_restores_defaults_and_persists(tmp_path: Path) -> None:
    """reset() must restore defaults, stamp updated_at, and persist."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)
    manager.update(
        active_project="Temp",
        running_tasks=["a", "b"],
        brain_mode="busy",
        conversation_state={"last_user_message": "x"},
    )

    reset_state = manager.reset()
    assert reset_state.active_project == "Titan"
    assert reset_state.running_tasks == []
    assert reset_state.brain_mode == "idle"
    assert reset_state.conversation_state["last_user_message"] is None
    assert reset_state.updated_at is not None

    reloaded = StateManager(file_path=file_path)
    assert reloaded.snapshot().active_project == "Titan"
    assert reloaded.snapshot().running_tasks == []


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Mutations saved by one instance must reload identically in a new instance."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)

    manager.update(
        active_project="Titan V2",
        progress="Phase 13.1",
        active_mission="State foundation",
        current_focus="persistence",
        active_tools=["json"],
        important_decisions=["single owner"],
    )

    reloaded = StateManager(file_path=file_path)
    snap = reloaded.snapshot()
    assert snap.active_project == "Titan V2"
    assert snap.progress == "Phase 13.1"
    assert snap.active_mission == "State foundation"
    assert snap.current_focus == "persistence"
    assert snap.active_tools == ["json"]
    assert snap.important_decisions == ["single owner"]
    assert file_path.exists()

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SCHEMA_VERSION
    _assert_required_fields(on_disk)


def test_save_writes_utf8_json(tmp_path: Path) -> None:
    """Persisted JSON must retain French/unicode content."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)
    manager.update(current_goal="Avancer concrètement")

    raw = file_path.read_text(encoding="utf-8")
    assert "Avancer concrètement" in raw
    assert "\\u" not in raw


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_concurrent_updates_are_thread_safe(tmp_path: Path) -> None:
    """Concurrent update/merge calls must not corrupt WorkspaceState."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            manager.update(current_focus=f"focus-{index}")
            manager.merge({"running_tasks": [f"task-{index}"]})
            manager.update_state("progress", f"progress-{index}")
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert errors == []
    snap = manager.snapshot()
    _assert_required_fields(snap)
    assert isinstance(snap.running_tasks, list)
    assert len(snap.running_tasks) == 1
    assert snap.updated_at is not None

    # File must remain valid JSON after concurrent writers.
    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert isinstance(on_disk, dict)
    _assert_required_fields(on_disk)


def test_concurrent_snapshots_see_consistent_copies(tmp_path: Path) -> None:
    """snapshot()/get_state() under contention must return consistent copies."""
    manager = StateManager(file_path=tmp_path / "titan_state.json")
    manager.update(active_project="Stable", running_tasks=["seed"])

    def reader(_: int) -> dict:
        snap = manager.snapshot()
        view = manager.get_state()
        assert snap.active_project == view["active_project"]
        assert list(snap.running_tasks) == list(view["running_tasks"])
        return view

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(reader, i) for i in range(40)]
        for future in as_completed(futures):
            result = future.result(timeout=5)
            assert result["active_project"] == "Stable"


def test_load_state_legacy_alias(tmp_path: Path) -> None:
    """load_state() legacy alias must return a dict with required fields."""
    manager = StateManager(file_path=tmp_path / "titan_state.json")
    payload = manager.load_state()
    assert isinstance(payload, dict)
    _assert_required_fields(payload)
    assert "last_user_message" in payload
    assert "last_titan_response" in payload

# =====================================
# Titan StateManager Tests
# =====================================

"""Baseline regression tests for StateManager load/save behavior."""

from __future__ import annotations

from pathlib import Path

from core.state_manager import StateManager

EXPECTED_DEFAULT_STATE = {
    "active_project": "Titan",
    "current_step": "Développement du State Manager",
    "last_user_message": None,
    "last_titan_response": None,
    "next_action": "Connecter le State Manager au Brain",
    "progress": "En développement",
}


def test_load_state_returns_default_schema_when_file_missing(
    tmp_path: Path,
) -> None:
    """Missing JSON file must yield the default schema without writing to disk."""
    file_path = tmp_path / "titan_state.json"
    assert not file_path.exists()

    manager = StateManager(file_path=file_path)

    assert manager.get_state() == EXPECTED_DEFAULT_STATE
    assert not file_path.exists()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Mutations saved by one instance must reload identically in a new instance."""
    file_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=file_path)

    manager.update_state("active_project", "Titan V2")
    manager.update_state("progress", "Phase 1")

    reloaded = StateManager(file_path=file_path)

    assert reloaded.get_state()["active_project"] == "Titan V2"
    assert reloaded.get_state()["progress"] == "Phase 1"
    assert file_path.exists()


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

    reloaded = StateManager(file_path=tmp_path / "titan_state.json")
    assert reloaded.get_state()["last_user_message"] == "Comment ça marche ?"
    assert reloaded.get_state()["last_titan_response"] == (
        "Voici comment ça fonctionne."
    )

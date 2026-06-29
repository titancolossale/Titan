# =====================================
# Titan Context Engine Tests
# =====================================

"""Tests for Phase 4 context engine (P4-050–P4-062)."""

from __future__ import annotations

import pytest

from context.context_engine import ContextEngine
from context.context_formatter import ContextFormatter
from context.context_manager import ContextManager
from context.models import ContextSnapshot
from context.session_manager import SessionManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager


def test_snapshot_syncs_from_active_mission(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-050: active mission step appears in current_phase."""
    state_manager.update_state("active_project", "Legacy Project")
    mission_manager.create_mission(
        "Brain Redesign",
        "Refactor the brain pipeline",
        ["Phase 4 context", "Phase 5 agents"],
    )

    engine = ContextEngine(state_manager, mission_manager)
    snapshot = engine.refresh()

    assert snapshot.mission_active is True
    assert snapshot.active_project == "Brain Redesign"
    assert snapshot.current_phase == "Phase 4 context"
    assert snapshot.current_goal == "Refactor the brain pipeline"


def test_snapshot_syncs_from_state_when_no_mission(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-051: without active mission, state fields are used."""
    state_manager.update_state("active_project", "Trading Bot")
    state_manager.update_state("current_step", "Backtest module")
    state_manager.update_state("next_action", "Implement risk controls")

    engine = ContextEngine(state_manager, mission_manager)
    snapshot = engine.refresh()

    assert snapshot.mission_active is False
    assert snapshot.active_project == "Trading Bot"
    assert snapshot.current_phase == "Backtest module"
    assert snapshot.current_goal == "Implement risk controls"


def test_mission_title_precedence_over_state_project(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-052: mission.title wins over state.active_project when mission active."""
    state_manager.update_state("active_project", "Stale Project")
    mission_manager.create_mission("Live Mission", "Do the thing", ["Step 1"])

    snapshot = ContextEngine(state_manager, mission_manager).refresh()

    assert snapshot.active_project == "Live Mission"


def test_snapshot_is_immutable(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-053: ContextSnapshot is frozen per turn."""
    snapshot = ContextEngine(state_manager, mission_manager).refresh()

    with pytest.raises(AttributeError):
        snapshot.current_user = "Ibrahim"  # type: ignore[misc]


def test_session_user_switch_nolan_to_ibrahim() -> None:
    """P4-054: /user Ibrahim changes active session user."""
    session = SessionManager(current_user="Nolan")

    success, message = session.set_user("Ibrahim")

    assert success is True
    assert session.current_user == "Ibrahim"
    assert "Ibrahim" in message


def test_session_rejects_unknown_user() -> None:
    """P4-055: unauthorized user names are rejected."""
    session = SessionManager()

    success, message = session.set_user("Alice")

    assert success is False
    assert session.current_user == "Nolan"
    assert "Alice" in message


def test_session_parse_user_command_variants() -> None:
    """P4-056: /user and utilisateur prefixes are recognized."""
    session = SessionManager()

    assert session.parse_user_command("/user Ibrahim") == "Ibrahim"
    assert session.parse_user_command("utilisateur Nolan") == "Nolan"
    assert session.parse_user_command("Bonjour") is None


def test_formatter_includes_french_labels() -> None:
    """P4-057: formatted output contains required French labels."""
    snapshot = ContextSnapshot(
        current_user="Nolan",
        active_project="Titan",
        current_goal="Ship context engine",
        current_phase="Phase 4",
        session_id="abc123",
        mode="interactive",
    )
    text = ContextFormatter().format(snapshot)

    for label in (
        "Utilisateur :",
        "Projet actif :",
        "Objectif :",
        "Phase actuelle :",
    ):
        assert label in text


def test_context_manager_refresh_returns_snapshot(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-058: ContextManager.refresh() returns typed snapshot."""
    ctx_mgr = ContextManager(state_manager, mission_manager)
    snapshot = ctx_mgr.refresh()

    assert isinstance(snapshot, ContextSnapshot)
    assert snapshot.current_user == "Nolan"


def test_context_manager_handle_session_command(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-059: session command switches user via facade."""
    ctx_mgr = ContextManager(state_manager, mission_manager)

    response = ctx_mgr.handle_session_command("/user Ibrahim")

    assert response is not None
    assert "Ibrahim" in response
    assert ctx_mgr.current_user == "Ibrahim"


def test_context_manager_pure_session_command_detection(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-060: pure /user commands are detected for LLM skip."""
    ctx_mgr = ContextManager(state_manager, mission_manager)

    assert ctx_mgr.is_pure_session_command("/user Ibrahim") is True
    assert ctx_mgr.is_pure_session_command("/user Ibrahim et autre chose") is False


def test_update_after_turn_records_last_action(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-061: post-turn hook records last user message on session."""
    ctx_mgr = ContextManager(state_manager, mission_manager)

    ctx_mgr.update_after_turn("Quelle est la prochaine étape ?", "Voici le plan.")

    assert ctx_mgr.session.last_action == "Quelle est la prochaine étape ?"


def test_refresh_produces_new_snapshot_when_state_changes(
    state_manager: StateManager,
    mission_manager: MissionManager,
) -> None:
    """P4-062: refresh reflects state updates within the same session."""
    engine = ContextEngine(state_manager, mission_manager)
    first = engine.refresh()

    state_manager.update_state("active_project", "Updated Project")
    second = engine.refresh()

    assert first.active_project != second.active_project
    assert second.active_project == "Updated Project"

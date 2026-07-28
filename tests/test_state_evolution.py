# =====================================
# Titan State Evolution Tests
# =====================================

"""Phase 13.3 — automatic WorkspaceState evolution during Brain.think()."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import ThinkContext
from brain.state_evolution import StateEvolutionEngine
from core.state_manager import StateManager, WorkspaceState


def _blank_workspace(**overrides: Any) -> WorkspaceState:
    """WorkspaceState with empty operational fields (no seed defaults)."""
    base = WorkspaceState(
        active_project=None,
        active_mission=None,
        current_step=None,
        current_goal=None,
        next_action=None,
        current_focus=None,
        brain_mode="idle",
        progress=None,
        conversation_state={
            "last_user_message": None,
            "last_titan_response": None,
        },
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_project_continuity_continue_message(brain: Brain) -> None:
    """'Continue {project}' must set active_project and working conversation status."""
    brain.state_manager.update(
        active_project=None,
        brain_mode="idle",
        conversation_state={"status": None},
    )

    brain.think("Continue Titan.")

    snap = brain.state_manager.snapshot()
    assert snap.active_project == "Titan"
    assert snap.conversation_state.get("status") == "working"
    assert snap.brain_mode == "working"
    assert snap.conversation_state["last_user_message"] == "Continue Titan."


def test_project_continuity_dynamic_name_not_hardcoded(brain: Brain) -> None:
    """Project name must be inferred from the message, not a hardcoded allowlist."""
    brain.state_manager.update(active_project=None)

    brain.think("Continue TradingBot.")

    snap = brain.state_manager.snapshot()
    assert snap.active_project == "TradingBot"
    assert snap.conversation_state.get("status") == "working"


def test_goal_evolution_from_working_message(brain: Brain) -> None:
    """Working-on messages must evolve current_goal from conversation understanding."""
    brain.state_manager.update(current_goal=None, current_focus=None)

    brain.think("We are fixing the State Manager.")

    snap = brain.state_manager.snapshot()
    assert snap.current_goal == "State Manager"
    assert snap.current_focus == "State Manager"


def test_step_evolution_from_working_message(brain: Brain) -> None:
    """Fixing/integrating intent must set current_step to Integration."""
    brain.state_manager.update(current_step=None)

    brain.think("We are fixing the State Manager.")

    snap = brain.state_manager.snapshot()
    assert snap.current_step == "Integration"


def test_progress_updates_and_clears_next_action(brain: Brain) -> None:
    """Finished signals must update progress and clear next_action."""
    brain.state_manager.update(
        progress="En développement",
        next_action="Connecter le State Manager au Brain",
        brain_mode="working",
    )

    brain.think("We finished this.")

    snap = brain.state_manager.snapshot()
    assert snap.progress == "Étape terminée"
    assert snap.next_action is None


def test_no_unnecessary_overwrite_of_valid_goal(brain: Brain) -> None:
    """Low-confidence / empty-signal turns must not clobber a valid current_goal."""
    brain.state_manager.update(
        current_goal="State Manager",
        current_step="Integration",
        active_project="Titan",
    )

    brain.think("Bonjour")

    snap = brain.state_manager.snapshot()
    assert snap.current_goal == "State Manager"
    assert snap.current_step == "Integration"
    assert snap.active_project == "Titan"


def test_mission_fills_empty_fields_only(brain: Brain) -> None:
    """Active mission may fill empty fields but must not overwrite high-value goals."""
    brain.mission_manager.create_mission(
        "Améliorer Titan",
        "Connecter le State Manager",
        ["Étape A", "Étape B"],
    )
    brain.state_manager.update(
        active_mission=None,
        current_goal="State Manager",
        current_step="Integration",
    )

    brain.think("Bonjour")

    snap = brain.state_manager.snapshot()
    assert snap.active_mission == "Améliorer Titan"
    assert snap.current_goal == "State Manager"
    assert snap.current_step == "Integration"


def test_state_evolution_diagnostics_emitted(
    brain: Brain,
    caplog: Any,
) -> None:
    """STATE_UPDATED / STATE_FIELD_CHANGED / STATE_NO_CHANGE diagnostics."""
    brain.state_manager.update(active_project=None)

    with caplog.at_level(logging.INFO, logger="brain.state_evolution"):
        brain.think("Continue Titan.")
        messages = [record.getMessage() for record in caplog.records]
        assert any(msg.startswith("STATE_UPDATED") for msg in messages)
        assert any(msg.startswith("STATE_FIELD_CHANGED") for msg in messages)

        caplog.clear()
        brain.state_manager.update(
            active_project="Titan",
            conversation_state={"status": "working"},
            brain_mode="working",
        )
        # Reload blank message path: greeting should not evolve operational fields.
        brain.think("Bonjour")
        messages = [record.getMessage() for record in caplog.records]
        assert any(msg.startswith("STATE_NO_CHANGE") for msg in messages)


def test_evolution_engine_unit_continue_and_finish() -> None:
    """Unit-level propose/apply for continue and finished patterns."""
    engine = StateEvolutionEngine()

    workspace = _blank_workspace()
    ctx = ThinkContext(user_message="Continue Titan.")
    ctx.workspace_state = workspace
    applied = engine.apply(ctx)
    assert any(u.field == "active_project" and u.value == "Titan" for u in applied)
    assert workspace.active_project == "Titan"
    assert workspace.conversation_state.get("status") == "working"

    workspace = _blank_workspace(
        next_action="Do something",
        progress="En cours",
    )
    ctx = ThinkContext(user_message="We finished this.")
    ctx.workspace_state = workspace
    applied = engine.apply(ctx)
    assert workspace.next_action is None
    assert workspace.progress == "Étape terminée"
    assert any(u.field == "next_action" for u in applied)


def test_evolution_persists_after_think(
    brain: Brain,
    tmp_path: Path,
) -> None:
    """Evolved fields must survive StateManager reload after think()."""
    brain.state_manager.update(current_goal=None, current_step=None)

    brain.think("We are fixing the State Manager.")

    reloaded = StateManager(file_path=tmp_path / "titan_state.json")
    snap = reloaded.snapshot()
    assert snap.current_goal == "State Manager"
    assert snap.current_step == "Integration"


def test_french_working_message_evolves_goal(brain: Brain) -> None:
    """French working-on phrasing must evolve goal and step."""
    brain.state_manager.update(current_goal=None, current_step=None)

    brain.think("On corrige le State Manager.")

    snap = brain.state_manager.snapshot()
    assert snap.current_goal == "State Manager"
    assert snap.current_step == "Integration"

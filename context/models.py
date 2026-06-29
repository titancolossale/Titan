# =====================================
# Titan Context Models
# =====================================

"""Typed structures for the context engine API (Phase 4 — P4-001)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextSnapshot:
    """Immutable situational model for one think() turn (P4-002).

    Built by ``ContextEngine.refresh()`` from state, mission, and session.
    Precedence when ``mission_active`` is True:

    - ``active_project`` ← mission.title, else state.active_project
    - ``current_phase`` ← mission.current_step, else state.current_step
    - ``current_goal`` ← mission.objective, else state.next_action

    When no active mission, all fields come from ``StateManager`` with defaults.
    """

    current_user: str
    active_project: str
    current_goal: str
    current_phase: str
    session_id: str
    mode: str
    last_action: str | None = None
    mission_active: bool = False
    mission_title: str | None = None

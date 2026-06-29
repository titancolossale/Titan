# =====================================
# Titan Context Engine
# =====================================

"""Aggregates state, mission, and session into situational context (Phase 4 — P4-010)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from context.context_formatter import ContextFormatter
from context.models import ContextSnapshot
from context.session_manager import SessionManager

if TYPE_CHECKING:
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager

_DEFAULT_PROJECT = "Titan"
_DEFAULT_PHASE = "Développement"
_DEFAULT_GOAL = "Continuer le développement de Titan."


class ContextEngine:
    """Builds ``ContextSnapshot`` from operational sources each turn.

    Precedence rules (documented for Phase 5+ routing):

    **Active mission** — mission fields win, state is fallback:

    - ``active_project`` ← ``mission.title`` → ``state.active_project`` → default
    - ``current_phase`` ← ``mission.current_step`` → ``state.current_step`` → default
    - ``current_goal`` ← ``mission.objective`` → ``state.next_action`` → default

    **No active mission** — state only with defaults:

    - ``active_project`` ← ``state.active_project``
    - ``current_phase`` ← ``state.current_step``
    - ``current_goal`` ← ``state.next_action``
    """

    def __init__(
        self,
        state_manager: StateManager,
        mission_manager: MissionManager,
        session_manager: SessionManager | None = None,
        formatter: ContextFormatter | None = None,
    ) -> None:
        self._state = state_manager
        self._mission = mission_manager
        self._session = session_manager or SessionManager()
        self._formatter = formatter or ContextFormatter()
        self._last_snapshot: ContextSnapshot | None = None

    @property
    def session(self) -> SessionManager:
        """Session identity owned by this engine."""
        return self._session

    @property
    def last_snapshot(self) -> ContextSnapshot | None:
        """Most recent snapshot from ``refresh()`` (frozen per turn)."""
        return self._last_snapshot

    def refresh(self) -> ContextSnapshot:
        """Aggregate current state + mission + session into a frozen snapshot."""
        state = self._state.get_state()
        mission = self._mission.get_mission()
        mission_active = bool(mission.get("active"))

        if mission_active:
            active_project = (
                mission.get("title")
                or state.get("active_project")
                or _DEFAULT_PROJECT
            )
            current_phase = (
                mission.get("current_step")
                or state.get("current_step")
                or _DEFAULT_PHASE
            )
            current_goal = (
                mission.get("objective")
                or state.get("next_action")
                or _DEFAULT_GOAL
            )
        else:
            active_project = state.get("active_project") or _DEFAULT_PROJECT
            current_phase = state.get("current_step") or _DEFAULT_PHASE
            current_goal = state.get("next_action") or _DEFAULT_GOAL

        snapshot = ContextSnapshot(
            current_user=self._session.current_user,
            active_project=str(active_project),
            current_goal=str(current_goal),
            current_phase=str(current_phase),
            session_id=self._session.session_id,
            mode=self._session.mode,
            last_action=self._session.last_action,
            mission_active=mission_active,
            mission_title=mission.get("title"),
        )
        self._last_snapshot = snapshot
        return snapshot

    def format_snapshot(self, snapshot: ContextSnapshot) -> str:
        """Format snapshot for prompt injection."""
        return self._formatter.format(snapshot)

    def get_context(self) -> str:
        """Refresh and return prompt-ready French context block."""
        return self.format_snapshot(self.refresh())

    def update_after_turn(self, user_message: str, response: str) -> None:
        """Post-response hook: record last action on session (P4-040)."""
        self._session.update_after_turn(user_message, response)

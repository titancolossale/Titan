# =====================================
# Titan Context Manager
# =====================================

"""Unified context facade — sole entry for Brain and composition root (Phase 4 — P4-030)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from context.context_engine import ContextEngine
from context.context_formatter import ContextFormatter
from context.models import ContextSnapshot
from context.session_manager import SessionManager

if TYPE_CHECKING:
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager


class ContextManager:
    """Facade over ``ContextEngine`` and ``SessionManager`` for backward compatibility."""

    def __init__(
        self,
        state_manager: StateManager,
        mission_manager: MissionManager,
        session_manager: SessionManager | None = None,
        engine: ContextEngine | None = None,
    ) -> None:
        self._session = session_manager or SessionManager()
        self._engine = engine or ContextEngine(
            state_manager=state_manager,
            mission_manager=mission_manager,
            session_manager=self._session,
        )

    @property
    def engine(self) -> ContextEngine:
        """Underlying context engine for advanced integration."""
        return self._engine

    @property
    def session(self) -> SessionManager:
        """Session manager for user identity."""
        return self._session

    @property
    def current_user(self) -> str:
        """Active session user (Nolan or Ibrahim)."""
        return self._session.current_user

    @property
    def active_project(self) -> str:
        """Active project from last refresh or state/mission sync."""
        snapshot = self._engine.last_snapshot or self._engine.refresh()
        return snapshot.active_project

    @property
    def current_goal(self) -> str:
        """Current goal from last refresh or state/mission sync."""
        snapshot = self._engine.last_snapshot or self._engine.refresh()
        return snapshot.current_goal

    @property
    def current_phase(self) -> str:
        """Current phase from last refresh or state/mission sync."""
        snapshot = self._engine.last_snapshot or self._engine.refresh()
        return snapshot.current_phase

    def refresh(self) -> ContextSnapshot:
        """Build frozen situational snapshot for the current turn."""
        return self._engine.refresh()

    def get_context(self) -> str:
        """Return French formatted context block for prompts."""
        return self._engine.get_context()

    def format_snapshot(self, snapshot: ContextSnapshot) -> str:
        """Format an existing snapshot for prompt injection."""
        return self._engine.format_snapshot(snapshot)

    def handle_session_command(self, message: str) -> str | None:
        """Handle ``/user`` commands; return French response when matched."""
        target = self._session.parse_user_command(message)
        if target is None:
            return None
        _success, response = self._session.set_user(target)
        return response

    def is_pure_session_command(self, message: str) -> bool:
        """True when message is only a user-switch command (skip LLM)."""
        return self._session.is_user_switch_command(message)

    def update_after_turn(self, user_message: str, response: str) -> None:
        """Post-response hook: update session last action."""
        self._engine.update_after_turn(user_message, response)

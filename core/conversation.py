# =====================================
# Titan Conversation Engine
# =====================================

"""Backward-compatible facade over ``ConversationEngine`` (Phase 7 — P7-020)."""

from __future__ import annotations

from typing import Any

from core.conversation_engine import ConversationEngine, TITAN_SPEAKER


class Conversation:
    """Thin wrapper preserving the legacy ``Conversation`` API."""

    def __init__(
        self,
        engine: ConversationEngine | None = None,
        *,
        session_id: str | None = None,
        persist_sessions: bool | None = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
        else:
            kwargs: dict[str, Any] = {}
            if session_id is not None:
                kwargs["session_id"] = session_id
            if persist_sessions is not None:
                kwargs["persist_sessions"] = persist_sessions
            self._engine = ConversationEngine(**kwargs)
        self._last_user = "Nolan"

    @property
    def engine(self) -> ConversationEngine:
        """Underlying conversation engine for Brain DI."""
        return self._engine

    @property
    def history(self) -> list[dict[str, str]]:
        """Legacy history list for callers expecting dict turns."""
        return [
            {"speaker": turn.speaker, "message": turn.message}
            for turn in self._engine.get_window()
        ]

    @property
    def turn_count(self) -> int:
        return self._engine.turn_count

    def add_message(self, speaker: str, message: str) -> None:
        if speaker == TITAN_SPEAKER:
            self._engine.add_titan_turn(message, user=self._last_user)
            return
        self._last_user = speaker
        self._engine.add_user_turn(speaker, message)

    def show_history(self) -> None:
        self._engine.show_history()

    def format_history(self) -> str:
        return self._engine.format_history()

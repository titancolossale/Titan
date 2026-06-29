# =====================================
# Titan Conversation Engine
# =====================================

"""Sliding-window dialogue history with prompt-safe formatting (Phase 7 — P7-011)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import (
    CONVERSATION_MAX_STORED_TURNS,
    CONVERSATION_PERSIST_SESSIONS,
    CONVERSATION_SUMMARIZE_THRESHOLD,
    CONVERSATION_WINDOW_SIZE,
    SESSIONS_DIR,
)
from core.conversation_models import ConversationTurn

TITAN_SPEAKER = "Titan"


class ConversationEngine:
    """Manages in-session dialogue turns, prompt windows, and optional persistence."""

    def __init__(
        self,
        *,
        session_id: str = "default",
        window_size: int = CONVERSATION_WINDOW_SIZE,
        max_stored_turns: int = CONVERSATION_MAX_STORED_TURNS,
        summarize_threshold: int = CONVERSATION_SUMMARIZE_THRESHOLD,
        persist_sessions: bool = CONVERSATION_PERSIST_SESSIONS,
        sessions_dir: Path | None = None,
    ) -> None:
        self._session_id = session_id
        self._window_size = window_size
        self._max_stored_turns = max_stored_turns
        self._summarize_threshold = summarize_threshold
        self._persist_sessions = persist_sessions
        self._sessions_dir = sessions_dir or SESSIONS_DIR
        self._turns: list[ConversationTurn] = []
        self._archived_summary: str | None = None
        self._archived_turn_count: int = 0

    @property
    def session_id(self) -> str:
        """Active session identifier."""
        return self._session_id

    @property
    def turn_count(self) -> int:
        """Total turns currently held in memory (excluding archived count)."""
        return len(self._turns)

    @property
    def total_turn_count(self) -> int:
        """Total turns including archived (summarized) turns."""
        return self._archived_turn_count + len(self._turns)

    def add_user_turn(self, user: str, message: str, *, metadata: dict[str, Any] | None = None) -> ConversationTurn:
        """Record a user message turn with speaker attribution (P7-012)."""
        turn = ConversationTurn(
            speaker=user,
            message=message.strip(),
            user=user,
            metadata=metadata or {},
        )
        self._append_turn(turn)
        return turn

    def add_titan_turn(
        self,
        message: str,
        *,
        user: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        """Record a Titan response turn (P7-012)."""
        turn = ConversationTurn(
            speaker=TITAN_SPEAKER,
            message=message.strip(),
            user=user,
            metadata=metadata or {},
        )
        self._append_turn(turn)
        return turn

    def add_message(self, speaker: str, message: str, *, user: str = "Nolan") -> ConversationTurn:
        """Backward-compatible alias — routes to user or Titan turn helpers (P7-020)."""
        if speaker == TITAN_SPEAKER:
            return self.add_titan_turn(message, user=user)
        return self.add_user_turn(speaker, message)

    def get_window(self, n: int | None = None) -> list[ConversationTurn]:
        """Return the last *n* turns in chronological order (P7-012)."""
        if n is None:
            return list(self._turns)
        if n <= 0:
            return []
        return list(self._turns[-n:])

    def get_prompt_window(
        self,
        n: int | None = None,
        *,
        current_message: str | None = None,
    ) -> list[str]:
        """Format turns for PromptBuilder, excluding duplicate current user message (P7-013)."""
        limit = n if n is not None else self._window_size
        turns = self.get_window(limit)
        if (
            current_message is not None
            and turns
            and turns[-1].speaker != TITAN_SPEAKER
            and turns[-1].message.strip() == current_message.strip()
        ):
            turns = turns[:-1]

        lines: list[str] = []
        if self._archived_summary:
            lines.append(
                f"[Résumé de {self._archived_turn_count} tours précédents] "
                f"{self._archived_summary}"
            )
        lines.extend(self._format_turn(turn) for turn in turns)
        return lines

    def clear(self) -> None:
        """Remove all in-memory turns and archived summary (P7-041)."""
        self._turns.clear()
        self._archived_summary = None
        self._archived_turn_count = 0
        if self._persist_sessions:
            self._delete_session_file()

    def session_status(self) -> str:
        """French session status summary for REPL (P7-042)."""
        return (
            f"Session : {self._session_id}\n"
            f"Tours en mémoire : {self.turn_count}\n"
            f"Tours totaux (session) : {self.total_turn_count}\n"
            f"Fenêtre prompt : {self._window_size} tours"
        )

    def handle_command(self, message: str) -> str | None:
        """Handle conversation REPL commands; return French response when matched (P7-041)."""
        stripped = message.strip()
        lower = stripped.lower()

        if lower in ("/clear", "/efface", "efface historique", "clear history"):
            self.clear()
            return "Historique de conversation effacé."

        if lower in ("/session", "statut session", "session status"):
            return self.session_status()

        if lower in ("/history", "historique", "show history"):
            return self.format_history()

        return None

    def is_pure_conversation_command(self, message: str) -> bool:
        """True when message is only a conversation command (skip LLM)."""
        stripped = message.strip().lower()
        return stripped in (
            "/clear",
            "/efface",
            "efface historique",
            "clear history",
            "/session",
            "statut session",
            "session status",
            "/history",
            "historique",
            "show history",
        )

    def format_history(self) -> str:
        """Return full formatted history for display."""
        if not self._turns and not self._archived_summary:
            return "Aucun historique de conversation."
        lines: list[str] = ["Historique de conversation :"]
        if self._archived_summary:
            lines.append(
                f"[Archivé — {self._archived_turn_count} tours] {self._archived_summary}"
            )
        lines.extend(self._format_turn(turn) for turn in self._turns)
        return "\n".join(lines)

    def show_history(self) -> None:
        """Print formatted history (backward-compatible REPL helper)."""
        print(self.format_history())

    def get_session_summary_for_memory(self, max_chars: int = 500) -> str | None:
        """Extractive session summary for MemoryService promotion path (P7-050)."""
        if not self._turns:
            return None
        snippets: list[str] = []
        for turn in self._turns[-6:]:
            prefix = f"{turn.speaker}:"
            text = turn.message.strip().replace("\n", " ")
            if len(text) > 120:
                text = text[:117] + "..."
            snippets.append(f"{prefix} {text}")
        summary = " | ".join(snippets)
        if self._archived_summary:
            summary = f"{self._archived_summary} | {summary}"
        if len(summary) > max_chars:
            return summary[: max_chars - 3] + "..."
        return summary

    def save_session(self) -> None:
        """Persist session turns to disk when enabled (P7-040)."""
        if not self._persist_sessions:
            return
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": self._session_id,
            "archived_summary": self._archived_summary,
            "archived_turn_count": self._archived_turn_count,
            "turns": [turn.to_dict() for turn in self._turns],
        }
        path = self._session_file_path()
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    def load_session(self) -> bool:
        """Load session from disk; return True when a file was found (P7-040)."""
        path = self._session_file_path()
        if not path.exists():
            return False
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        self._session_id = str(payload.get("session_id", self._session_id))
        self._archived_summary = payload.get("archived_summary")
        self._archived_turn_count = int(payload.get("archived_turn_count") or 0)
        self._turns = [
            ConversationTurn.from_dict(item)
            for item in payload.get("turns", [])
        ]
        return True

    def _append_turn(self, turn: ConversationTurn) -> None:
        self._turns.append(turn)
        self._maybe_archive_old_turns()
        if self._persist_sessions:
            self.save_session()

    def _maybe_archive_old_turns(self) -> None:
        """Collapse oldest turns into extractive summary when over threshold (P7-014)."""
        if len(self._turns) <= self._summarize_threshold:
            return
        overflow = len(self._turns) - self._max_stored_turns
        if overflow <= 0:
            return
        to_archive = self._turns[:overflow]
        self._turns = self._turns[overflow:]
        archived_text = self._extractive_summary(to_archive)
        if self._archived_summary:
            self._archived_summary = f"{self._archived_summary} {archived_text}"
        else:
            self._archived_summary = archived_text
        self._archived_turn_count += len(to_archive)
        if len(self._archived_summary) > 800:
            self._archived_summary = self._archived_summary[:797] + "..."

    @staticmethod
    def _extractive_summary(turns: list[ConversationTurn]) -> str:
        """Build a compact extractive summary from archived turns."""
        parts: list[str] = []
        for turn in turns:
            text = turn.message.strip().replace("\n", " ")
            if len(text) > 80:
                text = text[:77] + "..."
            parts.append(f"{turn.speaker}: {text}")
        return " ".join(parts)

    @staticmethod
    def _format_turn(turn: ConversationTurn) -> str:
        """Single-line prompt-safe turn formatting with speaker label."""
        return f"{turn.speaker} : {turn.message}"

    def _session_file_path(self) -> Path:
        return self._sessions_dir / f"{self._session_id}.json"

    def _delete_session_file(self) -> None:
        path = self._session_file_path()
        if path.exists():
            path.unlink()

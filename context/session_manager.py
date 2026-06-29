# =====================================
# Titan Session Manager
# =====================================

"""Session identity and mode for multi-user CLI sessions (Phase 4 — P4-003)."""

from __future__ import annotations

import uuid

AUTHORIZED_USERS: frozenset[str] = frozenset({"Nolan", "Ibrahim"})
DEFAULT_USER = "Nolan"
DEFAULT_MODE = "interactive"


class SessionManager:
    """Tracks current user, session id, and mode for the active REPL session."""

    def __init__(self, current_user: str = DEFAULT_USER) -> None:
        self._session_id = uuid.uuid4().hex[:8]
        self._current_user = self._normalize_user(current_user) or DEFAULT_USER
        self._mode = DEFAULT_MODE
        self._last_action: str | None = None

    @property
    def session_id(self) -> str:
        """Short stable identifier for this REPL session."""
        return self._session_id

    @property
    def current_user(self) -> str:
        """Canonical user name (Nolan or Ibrahim)."""
        return self._current_user

    @property
    def mode(self) -> str:
        """Session interaction mode (interactive today; voice hooks in Phase 10)."""
        return self._mode

    @property
    def last_action(self) -> str | None:
        """Last user message processed in this session."""
        return self._last_action

    @staticmethod
    def normalize_user(name: str) -> str | None:
        """Return canonical user name or None if not authorized."""
        cleaned = name.strip()
        if not cleaned:
            return None
        for authorized in AUTHORIZED_USERS:
            if cleaned.lower() == authorized.lower():
                return authorized
        return None

    _normalize_user = normalize_user

    def set_user(self, name: str) -> tuple[bool, str]:
        """Switch active user; returns (success, French user-facing message)."""
        normalized = self.normalize_user(name)
        if normalized is None:
            return False, (
                f"Utilisateur inconnu : {name.strip()}. "
                "Utilisateurs autorisés : Nolan, Ibrahim."
            )
        self._current_user = normalized
        return True, f"Utilisateur actif : {normalized}."

    def parse_user_command(self, message: str) -> str | None:
        """Extract target user from ``/user X`` or ``utilisateur X`` commands."""
        stripped = message.strip()
        lower = stripped.lower()
        for prefix in ("/user ", "utilisateur "):
            if lower.startswith(prefix):
                return stripped[len(prefix) :].strip()
        return None

    def is_user_switch_command(self, message: str) -> bool:
        """True when the message is solely a user-switch command."""
        stripped = message.strip()
        lower = stripped.lower()
        for prefix in ("/user ", "utilisateur "):
            if lower.startswith(prefix):
                remainder = stripped[len(prefix) :].strip()
                return self.normalize_user(remainder) is not None
        return False

    def update_after_turn(self, user_message: str, response: str) -> None:
        """Record last user action after a completed turn (P4-040)."""
        _ = response
        if user_message.strip():
            self._last_action = user_message.strip()[:200]

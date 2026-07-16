# =====================================
# Titan Web Session Manager
# =====================================

"""Server-side session store for private production authentication."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Final

SESSION_COOKIE_NAME: Final[str] = "titan_session"
CSRF_COOKIE_NAME: Final[str] = "titan_csrf"
CSRF_HEADER_NAME: Final[str] = "X-CSRF-Token"


@dataclass
class SessionRecord:
    """Authenticated session metadata (never stores passwords)."""

    session_id: str
    username: str
    created_at: float
    last_activity: float
    csrf_token: str
    revoked: bool = False


@dataclass
class SessionConfig:
    """Idle and absolute lifetime limits loaded from environment."""

    idle_minutes: int = 60
    max_hours: int = 24
    cookie_secure: bool = True
    cookie_samesite: str = "lax"

    @property
    def idle_seconds(self) -> float:
        return float(self.idle_minutes) * 60.0

    @property
    def max_seconds(self) -> float:
        return float(self.max_hours) * 3600.0


class SessionManager:
    """In-memory session registry with idle and absolute expiration."""

    def __init__(self, config: SessionConfig | None = None) -> None:
        self._config = config or SessionConfig()
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    @property
    def config(self) -> SessionConfig:
        return self._config

    def create_session(self, username: str) -> SessionRecord:
        """Create a new authenticated session for ``username``."""
        now = time.monotonic()
        record = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            username=username,
            created_at=now,
            last_activity=now,
            csrf_token=secrets.token_urlsafe(32),
        )
        with self._lock:
            self._sessions[record.session_id] = record
            self._purge_expired_unlocked(now)
        return record

    def get_session(self, session_id: str | None) -> SessionRecord | None:
        """Return a valid session or None if missing/expired/revoked."""
        if not session_id:
            return None
        now = time.monotonic()
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if record.revoked or self._is_expired(record, now):
                self._sessions.pop(session_id, None)
                return None
            record.last_activity = now
            return record

    def revoke_session(self, session_id: str | None) -> bool:
        """Invalidate a session. Returns True if a session was removed."""
        if not session_id:
            return False
        with self._lock:
            record = self._sessions.pop(session_id, None)
            if record is None:
                return False
            record.revoked = True
            return True

    def revoke_all_for_user(self, username: str) -> int:
        """Invalidate every session belonging to ``username``."""
        removed = 0
        with self._lock:
            stale = [
                sid
                for sid, record in self._sessions.items()
                if record.username == username
            ]
            for sid in stale:
                self._sessions.pop(sid, None)
                removed += 1
        return removed

    def validate_csrf(self, session: SessionRecord, token: str | None) -> bool:
        """Constant-time CSRF token comparison."""
        if not token:
            return False
        return secrets.compare_digest(session.csrf_token, token)

    def _is_expired(self, record: SessionRecord, now: float) -> bool:
        if (now - record.last_activity) > self._config.idle_seconds:
            return True
        if (now - record.created_at) > self._config.max_seconds:
            return True
        return False

    def _purge_expired_unlocked(self, now: float) -> None:
        expired = [
            sid
            for sid, record in self._sessions.items()
            if record.revoked or self._is_expired(record, now)
        ]
        for sid in expired:
            self._sessions.pop(sid, None)


_session_manager: SessionManager | None = None
_manager_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    """Return the process-wide session manager singleton."""
    global _session_manager
    with _manager_lock:
        if _session_manager is None:
            from api.auth_config import load_session_config

            _session_manager = SessionManager(load_session_config())
        return _session_manager


def reset_session_manager(manager: SessionManager | None = None) -> None:
    """Replace or clear the singleton (tests only)."""
    global _session_manager
    with _manager_lock:
        _session_manager = manager

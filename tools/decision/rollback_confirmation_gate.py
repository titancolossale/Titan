# =====================================
# Titan Tool Decision — Rollback Confirmation Gate
# =====================================

"""Explicit user confirmation for rollback operations (Phase 12 Batch 2 — P12B2-004)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

ACCEPTED_ROLLBACK_CONFIRMATIONS: frozenset[str] = frozenset({
    "confirm rollback",
    "confirme rollback",
    "approve rollback",
    "rollback confirm",
    "confirmer le rollback",
    "confirme le rollback",
})


def normalize_rollback_confirmation(message: str) -> str:
    """Normalize user input for rollback confirmation matching."""
    return message.strip().lower().rstrip(".")


def is_valid_rollback_confirmation(message: str) -> bool:
    """Return True only for explicitly accepted rollback confirmation phrases."""
    return normalize_rollback_confirmation(message) in ACCEPTED_ROLLBACK_CONFIRMATIONS


@dataclass(frozen=True)
class PendingRollback:
    """Registered rollback target awaiting user confirmation."""

    token: str
    rollback_id: str
    session_id: str


@dataclass
class RollbackConfirmationGate:
    """In-memory store for rollback operations pending user approval."""

    _pending: dict[str, PendingRollback] = field(default_factory=dict)
    _session_latest: dict[str, str] = field(default_factory=dict)

    def register(
        self,
        rollback_id: str,
        *,
        session_id: str = "default",
    ) -> str:
        """Register a rollback target and return its confirmation token."""
        token = uuid.uuid4().hex[:12]
        entry = PendingRollback(
            token=token,
            rollback_id=rollback_id,
            session_id=session_id,
        )
        self._pending[token] = entry
        self._session_latest[session_id] = token
        return token

    def get_latest(self, *, session_id: str = "default") -> PendingRollback | None:
        """Return the most recently registered pending rollback for a session."""
        token = self._session_latest.get(session_id)
        if token is None:
            return None
        return self._pending.get(token)

    def consume(self, token: str) -> PendingRollback | None:
        """Remove and return pending rollback after successful restore."""
        entry = self._pending.pop(token, None)
        if entry is not None:
            latest = self._session_latest.get(entry.session_id)
            if latest == token:
                self._session_latest.pop(entry.session_id, None)
        return entry

    def clear(self) -> None:
        """Reset all pending rollbacks (for tests)."""
        self._pending.clear()
        self._session_latest.clear()


_default_gate = RollbackConfirmationGate()


def get_rollback_confirmation_gate() -> RollbackConfirmationGate:
    """Return the process-wide rollback confirmation gate."""
    return _default_gate

# =====================================
# Titan Tool Decision — Patch Confirmation Gate
# =====================================

"""Explicit user confirmation for patch application (Phase 12 — P12-002)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from tools.decision.modification_models import ModificationPlan

ACCEPTED_PATCH_CONFIRMATIONS: frozenset[str] = frozenset({
    "approve",
    "approved",
    "confirm",
    "apply patch",
    "applique le patch",
    "vas-y applique",
})


def normalize_confirmation_message(message: str) -> str:
    """Normalize user input for exact confirmation matching."""
    return message.strip().lower().rstrip(".")


def is_valid_patch_confirmation(message: str) -> bool:
    """Return True only for explicitly accepted confirmation phrases (P12-002)."""
    return normalize_confirmation_message(message) in ACCEPTED_PATCH_CONFIRMATIONS


@dataclass(frozen=True)
class PendingPatchPlan:
    """Registered modification plan awaiting user confirmation."""

    token: str
    plan: ModificationPlan
    session_id: str


@dataclass
class PatchConfirmationGate:
    """In-memory store for modification plans pending user approval."""

    _pending: dict[str, PendingPatchPlan] = field(default_factory=dict)
    _session_latest: dict[str, str] = field(default_factory=dict)

    def register_plan(
        self,
        plan: ModificationPlan,
        *,
        session_id: str = "default",
    ) -> str:
        """Register a plan and return its confirmation token."""
        token = uuid.uuid4().hex[:12]
        entry = PendingPatchPlan(token=token, plan=plan, session_id=session_id)
        self._pending[token] = entry
        self._session_latest[session_id] = token
        return token

    def lookup(self, token: str) -> PendingPatchPlan | None:
        """Return pending plan for token without consuming it."""
        return self._pending.get(token)

    def get_latest(self, *, session_id: str = "default") -> PendingPatchPlan | None:
        """Return the most recently registered plan for a session."""
        token = self._session_latest.get(session_id)
        if token is None:
            return None
        return self._pending.get(token)

    def consume(self, token: str) -> PendingPatchPlan | None:
        """Remove and return pending plan after successful application."""
        entry = self._pending.pop(token, None)
        if entry is not None:
            latest = self._session_latest.get(entry.session_id)
            if latest == token:
                self._session_latest.pop(entry.session_id, None)
        return entry

    def clear(self) -> None:
        """Reset all pending plans (for tests)."""
        self._pending.clear()
        self._session_latest.clear()


_default_gate = PatchConfirmationGate()


def get_patch_confirmation_gate() -> PatchConfirmationGate:
    """Return the process-wide patch confirmation gate."""
    return _default_gate

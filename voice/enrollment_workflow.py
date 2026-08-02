# =====================================
# Titan Production Enrollment Workflow
# =====================================

"""Production enrollment state machine (Phase 20.10A).

Maps the guided enrollment service onto an explicit production workflow
without replacing Phase 20.2–20.9 lifecycle status values used by APIs/tests.

Does not collect real Nolan/Ibrahim voices — workflow preparation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from voice.enrollment_models import EnrollmentStatus
from voice.exceptions import VoiceEnrollmentError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


class ProductionEnrollmentState(str, Enum):
    """Complete production enrollment workflow states."""

    WAITING_CONSENT = "WAITING_CONSENT"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    READY_TO_RECORD = "READY_TO_RECORD"
    RECORDING = "RECORDING"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECOVERY = "RECOVERY"


# Explicit allowed transitions (production state machine).
ALLOWED_TRANSITIONS: dict[ProductionEnrollmentState, frozenset[ProductionEnrollmentState]] = {
    ProductionEnrollmentState.WAITING_CONSENT: frozenset(
        {
            ProductionEnrollmentState.CONSENT_GRANTED,
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.RECOVERY,
        }
    ),
    ProductionEnrollmentState.CONSENT_GRANTED: frozenset(
        {
            ProductionEnrollmentState.READY_TO_RECORD,
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.RECOVERY,
        }
    ),
    ProductionEnrollmentState.READY_TO_RECORD: frozenset(
        {
            ProductionEnrollmentState.RECORDING,
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.RECOVERY,
            ProductionEnrollmentState.FAILED,
        }
    ),
    ProductionEnrollmentState.RECORDING: frozenset(
        {
            ProductionEnrollmentState.READY_TO_RECORD,
            ProductionEnrollmentState.VERIFYING,
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.RECOVERY,
            ProductionEnrollmentState.FAILED,
        }
    ),
    ProductionEnrollmentState.VERIFYING: frozenset(
        {
            ProductionEnrollmentState.SUCCESS,
            ProductionEnrollmentState.FAILED,
            ProductionEnrollmentState.VERIFYING,  # retry in-place
            ProductionEnrollmentState.READY_TO_RECORD,  # collect more then re-verify
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.RECOVERY,
        }
    ),
    ProductionEnrollmentState.RECOVERY: frozenset(
        {
            ProductionEnrollmentState.WAITING_CONSENT,
            ProductionEnrollmentState.CONSENT_GRANTED,
            ProductionEnrollmentState.READY_TO_RECORD,
            ProductionEnrollmentState.RECORDING,
            ProductionEnrollmentState.VERIFYING,
            ProductionEnrollmentState.CANCELLED,
            ProductionEnrollmentState.FAILED,
        }
    ),
    ProductionEnrollmentState.SUCCESS: frozenset(),
    ProductionEnrollmentState.FAILED: frozenset(
        {
            ProductionEnrollmentState.WAITING_CONSENT,  # new attempt
            ProductionEnrollmentState.VERIFYING,  # reopen verify; keep pending profile
            ProductionEnrollmentState.CANCELLED,
        }
    ),
    ProductionEnrollmentState.CANCELLED: frozenset(
        {
            ProductionEnrollmentState.WAITING_CONSENT,  # new attempt
        }
    ),
}


# Legacy EnrollmentStatus ↔ production workflow mapping.
_LEGACY_TO_PRODUCTION: dict[EnrollmentStatus, ProductionEnrollmentState] = {
    EnrollmentStatus.NOT_ENROLLED: ProductionEnrollmentState.WAITING_CONSENT,
    EnrollmentStatus.AWAITING_CONSENT: ProductionEnrollmentState.WAITING_CONSENT,
    EnrollmentStatus.COLLECTING: ProductionEnrollmentState.READY_TO_RECORD,
    EnrollmentStatus.VALIDATING: ProductionEnrollmentState.RECORDING,
    EnrollmentStatus.BUILDING_PROFILE: ProductionEnrollmentState.RECORDING,
    EnrollmentStatus.VERIFYING: ProductionEnrollmentState.VERIFYING,
    EnrollmentStatus.ENROLLED: ProductionEnrollmentState.SUCCESS,
    EnrollmentStatus.FAILED: ProductionEnrollmentState.FAILED,
    EnrollmentStatus.CANCELLED: ProductionEnrollmentState.CANCELLED,
    EnrollmentStatus.REVOKED: ProductionEnrollmentState.CANCELLED,
}

_PRODUCTION_TO_LEGACY: dict[ProductionEnrollmentState, EnrollmentStatus] = {
    ProductionEnrollmentState.WAITING_CONSENT: EnrollmentStatus.AWAITING_CONSENT,
    ProductionEnrollmentState.CONSENT_GRANTED: EnrollmentStatus.COLLECTING,
    ProductionEnrollmentState.READY_TO_RECORD: EnrollmentStatus.COLLECTING,
    ProductionEnrollmentState.RECORDING: EnrollmentStatus.VALIDATING,
    ProductionEnrollmentState.VERIFYING: EnrollmentStatus.VERIFYING,
    ProductionEnrollmentState.SUCCESS: EnrollmentStatus.ENROLLED,
    ProductionEnrollmentState.FAILED: EnrollmentStatus.FAILED,
    ProductionEnrollmentState.CANCELLED: EnrollmentStatus.CANCELLED,
    ProductionEnrollmentState.RECOVERY: EnrollmentStatus.COLLECTING,
}


TERMINAL_PRODUCTION_STATES = frozenset(
    {
        ProductionEnrollmentState.SUCCESS,
        ProductionEnrollmentState.FAILED,
        ProductionEnrollmentState.CANCELLED,
    }
)

IN_FLIGHT_PRODUCTION_STATES = frozenset(
    {
        ProductionEnrollmentState.WAITING_CONSENT,
        ProductionEnrollmentState.CONSENT_GRANTED,
        ProductionEnrollmentState.READY_TO_RECORD,
        ProductionEnrollmentState.RECORDING,
        ProductionEnrollmentState.VERIFYING,
        ProductionEnrollmentState.RECOVERY,
    }
)


def legacy_to_production(status: EnrollmentStatus) -> ProductionEnrollmentState:
    """Map a Phase 20.2–20.9 status onto the production workflow state."""
    return _LEGACY_TO_PRODUCTION.get(status, ProductionEnrollmentState.FAILED)


def production_to_legacy(state: ProductionEnrollmentState) -> EnrollmentStatus:
    """Map a production workflow state onto the legacy enrollment status."""
    return _PRODUCTION_TO_LEGACY.get(state, EnrollmentStatus.FAILED)


@dataclass
class WorkflowTransition:
    """One audited workflow transition (safe metadata only)."""

    transition_id: str
    from_state: ProductionEnrollmentState
    to_state: ProductionEnrollmentState
    reason: str
    attempt_number: int = 1
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "attempt_number": self.attempt_number,
            "created_at": _iso(self.created_at),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowTransition:
        return cls(
            transition_id=str(data.get("transition_id") or uuid4()),
            from_state=ProductionEnrollmentState(
                str(data.get("from_state", ProductionEnrollmentState.FAILED.value))
            ),
            to_state=ProductionEnrollmentState(
                str(data.get("to_state", ProductionEnrollmentState.FAILED.value))
            ),
            reason=str(data.get("reason") or ""),
            attempt_number=int(data.get("attempt_number", 1)),
            created_at=(
                datetime.fromisoformat(str(data["created_at"]))
                if data.get("created_at")
                else _utc_now()
            ),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class EnrollmentWorkflowSnapshot:
    """Safe public view of the production enrollment workflow."""

    workflow_state: ProductionEnrollmentState
    legacy_status: EnrollmentStatus
    attempt_number: int
    can_record: bool
    can_verify: bool
    can_cancel: bool
    can_recover: bool
    is_terminal: bool
    transitions: tuple[WorkflowTransition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_state": self.workflow_state.value,
            "legacy_status": self.legacy_status.value,
            "attempt_number": self.attempt_number,
            "can_record": self.can_record,
            "can_verify": self.can_verify,
            "can_cancel": self.can_cancel,
            "can_recover": self.can_recover,
            "is_terminal": self.is_terminal,
            "allowed_next": [
                s.value for s in sorted(ALLOWED_TRANSITIONS.get(self.workflow_state, frozenset()), key=lambda x: x.value)
            ],
            "transitions": [t.to_dict() for t in self.transitions[-20:]],
        }


class EnrollmentWorkflowController:
    """Validates and records production enrollment state transitions."""

    def __init__(self) -> None:
        self._history: list[WorkflowTransition] = []

    @property
    def history(self) -> list[WorkflowTransition]:
        return list(self._history)

    def load_history(self, events: list[dict[str, Any]] | list[WorkflowTransition]) -> None:
        self._history = []
        for item in events:
            if isinstance(item, WorkflowTransition):
                self._history.append(item)
            elif isinstance(item, dict):
                self._history.append(WorkflowTransition.from_dict(item))

    def export_history(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._history]

    def can_transition(
        self,
        current: ProductionEnrollmentState,
        target: ProductionEnrollmentState,
    ) -> bool:
        if current == target and current == ProductionEnrollmentState.VERIFYING:
            return True
        return target in ALLOWED_TRANSITIONS.get(current, frozenset())

    def transition(
        self,
        current: ProductionEnrollmentState,
        target: ProductionEnrollmentState,
        *,
        reason: str,
        attempt_number: int = 1,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> WorkflowTransition:
        """Apply a production workflow transition or raise."""
        if current == target and not force:
            # Idempotent no-op still recorded for diagnostics when forced.
            if target != ProductionEnrollmentState.VERIFYING:
                return WorkflowTransition(
                    transition_id=str(uuid4()),
                    from_state=current,
                    to_state=target,
                    reason=reason or "noop",
                    attempt_number=attempt_number,
                    metadata=dict(metadata or {}),
                )
        if not force and not self.can_transition(current, target):
            raise VoiceEnrollmentError(
                f"Invalid enrollment workflow transition "
                f"{current.value} → {target.value}",
                code="invalid_workflow_transition",
            )
        event = WorkflowTransition(
            transition_id=str(uuid4()),
            from_state=current,
            to_state=target,
            reason=reason,
            attempt_number=attempt_number,
            metadata=dict(metadata or {}),
        )
        self._history.append(event)
        return event

    def snapshot(
        self,
        *,
        workflow_state: ProductionEnrollmentState,
        legacy_status: EnrollmentStatus,
        attempt_number: int = 1,
    ) -> EnrollmentWorkflowSnapshot:
        terminal = workflow_state in TERMINAL_PRODUCTION_STATES
        return EnrollmentWorkflowSnapshot(
            workflow_state=workflow_state,
            legacy_status=legacy_status,
            attempt_number=attempt_number,
            can_record=workflow_state
            in {
                ProductionEnrollmentState.READY_TO_RECORD,
                ProductionEnrollmentState.RECORDING,
                ProductionEnrollmentState.RECOVERY,
            },
            can_verify=workflow_state == ProductionEnrollmentState.VERIFYING,
            can_cancel=workflow_state not in TERMINAL_PRODUCTION_STATES
            or workflow_state == ProductionEnrollmentState.FAILED,
            can_recover=workflow_state in IN_FLIGHT_PRODUCTION_STATES
            or workflow_state == ProductionEnrollmentState.RECOVERY,
            is_terminal=terminal,
            transitions=tuple(self._history),
        )

    @staticmethod
    def initial_state(*, consent_given: bool) -> ProductionEnrollmentState:
        if consent_given:
            return ProductionEnrollmentState.READY_TO_RECORD
        return ProductionEnrollmentState.WAITING_CONSENT

    @staticmethod
    def after_consent_granted() -> tuple[
        ProductionEnrollmentState, ProductionEnrollmentState
    ]:
        """Return (CONSENT_GRANTED, then READY_TO_RECORD) sequence targets."""
        return (
            ProductionEnrollmentState.CONSENT_GRANTED,
            ProductionEnrollmentState.READY_TO_RECORD,
        )

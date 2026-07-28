# =====================================
# Titan Execution Recovery
# =====================================

"""Execution recovery, retry, rollback, and resume (Phase 18.4).

Determines whether a failed or interrupted ExecutionTask should retry,
rollback, abort, wait, ask the user, or mark partial success.

Reuses ExecutionSafety / Tool Execution Bridge outcomes — does not recreate
those systems. Persistence is a single lightweight checkpoint file.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from brain.execution_models import ExecutionStatus
from brain.execution_tool_models import BridgeExecutionResult, BridgeExecutionStatus

logger = logging.getLogger(__name__)

# Structured diagnostic event prefixes (Phase 18.4).
DIAG_EXECUTION_RETRY = "EXECUTION_RETRY"
DIAG_EXECUTION_RESUME = "EXECUTION_RESUME"
DIAG_EXECUTION_ABORT = "EXECUTION_ABORT"
DIAG_EXECUTION_ROLLBACK = "EXECUTION_ROLLBACK"
DIAG_EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
DIAG_EXECUTION_RECOVERED = "EXECUTION_RECOVERED"

_RETRYABLE_MARKERS = (
    "timeout",
    "temporar",
    "rate limit",
    "connexion",
    "connection",
    "unavailable",
    "indisponible",
    "retry",
    "transient",
    "busy",
    "overloaded",
)


class RecoveryAction(str, Enum):
    """Post-failure / interrupt recovery choice."""

    RETRY = "RETRY"
    ROLLBACK = "ROLLBACK"
    ABORT = "ABORT"
    WAIT = "WAIT"
    REQUEST_USER = "REQUEST_USER"
    MARK_PARTIAL_SUCCESS = "MARK_PARTIAL_SUCCESS"


class RollbackStatus(str, Enum):
    """Lifecycle of a stored rollback record."""

    NONE = "NONE"
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class ExecutionRetryPolicy:
    """Configurable retry policy for ExecutionEngine recovery."""

    max_attempts: int = 3
    retry_delay: float = 0.05
    backoff_multiplier: float = 2.0
    retry_reason: str | None = None
    attempt_number: int = 0
    retry_on_timeout: bool = True

    def delay_for_attempt(self, attempt_number: int) -> float:
        """Compute sleep seconds before the next attempt (1-based attempt)."""
        base = max(0.0, float(self.retry_delay))
        mult = max(1.0, float(self.backoff_multiplier))
        # attempt_number is the completed attempt; delay for the next try.
        exponent = max(0, int(attempt_number) - 1)
        return base * (mult ** exponent)

    def can_retry(self, attempt_number: int) -> bool:
        return int(attempt_number) < max(1, int(self.max_attempts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "retry_delay": self.retry_delay,
            "backoff_multiplier": self.backoff_multiplier,
            "retry_reason": self.retry_reason,
            "attempt_number": self.attempt_number,
            "retry_on_timeout": self.retry_on_timeout,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ExecutionRetryPolicy:
        raw = dict(data or {})
        return cls(
            max_attempts=max(1, int(raw.get("max_attempts", 3))),
            retry_delay=max(0.0, float(raw.get("retry_delay", 0.05))),
            backoff_multiplier=max(1.0, float(raw.get("backoff_multiplier", 2.0))),
            retry_reason=raw.get("retry_reason"),
            attempt_number=max(0, int(raw.get("attempt_number", 0))),
            retry_on_timeout=bool(raw.get("retry_on_timeout", True)),
        )


@dataclass
class RollbackRecord:
    """Stored rollback information for a reversible tool execution."""

    rollback_id: str | None = None
    tool_id: str | None = None
    action_id: str | None = None
    rollback_status: RollbackStatus = RollbackStatus.NONE
    rollback_reason: str | None = None
    rollback_completed: bool = False
    reversible: bool = False
    # Lightweight public metadata only — never secrets / raw payloads.
    public_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "tool_id": self.tool_id,
            "action_id": self.action_id,
            "rollback_status": self.rollback_status.value,
            "rollback_reason": self.rollback_reason,
            "rollback_completed": self.rollback_completed,
            "reversible": self.reversible,
            "public_token": self.public_token,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> RollbackRecord:
        raw = dict(data or {})
        status_raw = raw.get("rollback_status", RollbackStatus.NONE.value)
        try:
            status = RollbackStatus(str(status_raw))
        except ValueError:
            status = RollbackStatus.NONE
        return cls(
            rollback_id=raw.get("rollback_id"),
            tool_id=raw.get("tool_id"),
            action_id=raw.get("action_id"),
            rollback_status=status,
            rollback_reason=raw.get("rollback_reason"),
            rollback_completed=bool(raw.get("rollback_completed", False)),
            reversible=bool(raw.get("reversible", False)),
            public_token=raw.get("public_token"),
        )

    @classmethod
    def from_bridge_result(
        cls,
        result: BridgeExecutionResult,
        *,
        reason: str | None = None,
    ) -> RollbackRecord | None:
        """Build a rollback record when the bridge reports a reversible run."""
        if not getattr(result, "reversible", False):
            return None
        token = getattr(result, "rollback_token", None)
        if not token and not getattr(result, "reversible", False):
            return None
        return cls(
            rollback_id=str(token) if token else None,
            tool_id=result.tool_id,
            action_id=result.action_id,
            rollback_status=RollbackStatus.AVAILABLE,
            rollback_reason=reason or "Tool reported reversible execution",
            rollback_completed=False,
            reversible=True,
            public_token=str(token) if token else None,
        )


@dataclass(frozen=True)
class RecoveryDecision:
    """Outcome of recovery classification for one failure / interrupt."""

    action: RecoveryAction
    reason: str
    retry_reason: str | None = None
    attempt_number: int = 0
    delay_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "retry_reason": self.retry_reason,
            "attempt_number": self.attempt_number,
            "delay_seconds": self.delay_seconds,
        }


@dataclass
class ExecutionCheckpoint:
    """Lightweight persisted execution state for resume-after-restart."""

    task_id: str
    action: str | None
    status: str
    decision_id: str | None = None
    attempt_number: int = 0
    last_failure_reason: str | None = None
    recovery_action: str | None = None
    irreversible_fingerprint: str | None = None
    rollback: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    resumable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "status": self.status,
            "decision_id": self.decision_id,
            "attempt_number": self.attempt_number,
            "last_failure_reason": self.last_failure_reason,
            "recovery_action": self.recovery_action,
            "irreversible_fingerprint": self.irreversible_fingerprint,
            "rollback": self.rollback,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resumable": self.resumable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ExecutionCheckpoint | None:
        if not data:
            return None
        task_id = data.get("task_id")
        if not task_id:
            return None
        return cls(
            task_id=str(task_id),
            action=data.get("action"),
            status=str(data.get("status") or ExecutionStatus.FAILED.value),
            decision_id=data.get("decision_id"),
            attempt_number=max(0, int(data.get("attempt_number", 0))),
            last_failure_reason=data.get("last_failure_reason"),
            recovery_action=data.get("recovery_action"),
            irreversible_fingerprint=data.get("irreversible_fingerprint"),
            rollback=dict(data["rollback"])
            if isinstance(data.get("rollback"), Mapping)
            else None,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            resumable=bool(data.get("resumable", True)),
        )


@dataclass
class RecoveryState:
    """In-memory recovery mirror for the active ExecutionTask."""

    current_retry: int = 0
    retry_count: int = 0
    rollback_available: bool = False
    execution_recovered: bool = False
    last_failure_reason: str | None = None
    last_recovery_action: RecoveryAction | None = None
    rollback: RollbackRecord | None = None
    policy: ExecutionRetryPolicy = field(default_factory=ExecutionRetryPolicy)

    def format_for_prompt(self) -> str:
        """Prompt block — only the four Phase 18.4 public fields."""
        failure = self.last_failure_reason or "None"
        return "\n".join(
            [
                "Execution Recovery",
                f"Retry Count: {self.retry_count}",
                f"Rollback Available: {'yes' if self.rollback_available else 'no'}",
                f"Current Failure: {failure}",
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_retry": self.current_retry,
            "retry_count": self.retry_count,
            "rollback_available": self.rollback_available,
            "execution_recovered": self.execution_recovered,
            "last_failure_reason": self.last_failure_reason,
            "last_recovery_action": (
                self.last_recovery_action.value if self.last_recovery_action else None
            ),
            "rollback": self.rollback.to_dict() if self.rollback else None,
            "policy": self.policy.to_dict(),
        }


class ExecutionRecoveryManager:
    """Classify failures, track retries, store rollback info, persist resume state."""

    def __init__(
        self,
        *,
        policy: ExecutionRetryPolicy | None = None,
        checkpoint_path: str | Path | None = None,
        sleep_fn: Any | None = None,
    ) -> None:
        self._policy = policy or ExecutionRetryPolicy()
        self._checkpoint_path = (
            Path(checkpoint_path) if checkpoint_path is not None else None
        )
        self._sleep = sleep_fn or time.sleep
        self._state = RecoveryState(policy=self._policy)
        # Fingerprints of irreversible actions that already ran — never re-run.
        self._irreversible_executed: set[str] = set()
        self._checkpoint: ExecutionCheckpoint | None = None

    @property
    def policy(self) -> ExecutionRetryPolicy:
        return self._policy

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def checkpoint(self) -> ExecutionCheckpoint | None:
        return self._checkpoint

    def reset_for_task(self) -> None:
        """Clear per-task counters while preserving irreversible fingerprints."""
        self._state = RecoveryState(policy=self._policy)
        self._checkpoint = None

    def decide(
        self,
        *,
        bridge_result: BridgeExecutionResult | None,
        status: ExecutionStatus,
        attempt_number: int,
        safety_reversible: bool | None = None,
        action_metadata: Mapping[str, Any] | None = None,
        was_confirmation_failure: bool = False,
        was_forbidden: bool = False,
    ) -> RecoveryDecision:
        """Choose the recovery action for a non-success outcome."""
        meta = dict(action_metadata or {})
        failure = _failure_text(bridge_result, status)

        if was_forbidden or status == ExecutionStatus.FORBIDDEN:
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason="Forbidden failures are never retried",
                attempt_number=attempt_number,
            )

        if was_confirmation_failure or status == ExecutionStatus.AWAITING_CONFIRMATION:
            return RecoveryDecision(
                action=RecoveryAction.REQUEST_USER,
                reason="Confirmation required — never auto-retry",
                attempt_number=attempt_number,
            )

        if status in (ExecutionStatus.BLOCKED,):
            # Permission / confirmation blocks are not transient.
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason="Blocked executions are not retried",
                attempt_number=attempt_number,
            )

        if status == ExecutionStatus.PARTIAL_SUCCESS or (
            bridge_result is not None
            and bridge_result.status == BridgeExecutionStatus.PARTIAL_SUCCESS
        ):
            return RecoveryDecision(
                action=RecoveryAction.MARK_PARTIAL_SUCCESS,
                reason="Partial success — preserve progress without full retry",
                attempt_number=attempt_number,
            )

        explicit = meta.get("recovery_action") or meta.get("on_failure")
        if explicit:
            mapped = _parse_recovery_action(explicit)
            if mapped is not None:
                return RecoveryDecision(
                    action=mapped,
                    reason=f"Explicit recovery_action={mapped.value}",
                    retry_reason=str(meta.get("retry_reason") or failure or ""),
                    attempt_number=attempt_number,
                    delay_seconds=self._policy.delay_for_attempt(attempt_number)
                    if mapped == RecoveryAction.RETRY
                    else 0.0,
                )

        if status == ExecutionStatus.TIMEOUT or (
            bridge_result is not None
            and bridge_result.status == BridgeExecutionStatus.TIMEOUT
        ):
            logger.info(
                "%s attempt=%s reason=%s",
                DIAG_EXECUTION_TIMEOUT,
                attempt_number,
                failure,
            )
            if self._policy.retry_on_timeout and self._policy.can_retry(attempt_number):
                delay = self._policy.delay_for_attempt(attempt_number)
                return RecoveryDecision(
                    action=RecoveryAction.RETRY,
                    reason="Timeout — retryable",
                    retry_reason=failure or "timeout",
                    attempt_number=attempt_number,
                    delay_seconds=delay,
                )
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason="Timeout — retry limit reached or retries disabled",
                attempt_number=attempt_number,
            )

        reversible = bool(
            getattr(bridge_result, "reversible", False)
            if bridge_result is not None
            else False
        )
        if safety_reversible is False and not reversible:
            # Irreversible failure after side effects — do not retry blindly.
            if failure and _is_retryable_text(failure) and self._policy.can_retry(
                attempt_number
            ):
                # Still allow transient infra retries when no side effect confirmed.
                pass
            elif not _is_retryable_text(failure or ""):
                return RecoveryDecision(
                    action=RecoveryAction.ABORT,
                    reason="Irreversible failure — abort without retry",
                    attempt_number=attempt_number,
                )

        if reversible and meta.get("prefer_rollback") is True:
            return RecoveryDecision(
                action=RecoveryAction.ROLLBACK,
                reason="Reversible execution — rollback preferred",
                attempt_number=attempt_number,
            )

        if meta.get("wait") is True or meta.get("resume_later") is True:
            return RecoveryDecision(
                action=RecoveryAction.WAIT,
                reason="Execution deferred — wait / resume later",
                attempt_number=attempt_number,
            )

        if meta.get("request_user") is True:
            return RecoveryDecision(
                action=RecoveryAction.REQUEST_USER,
                reason="User intervention requested",
                attempt_number=attempt_number,
            )

        if _is_retryable_text(failure or "") and self._policy.can_retry(attempt_number):
            delay = self._policy.delay_for_attempt(attempt_number)
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                reason="Retryable failure",
                retry_reason=failure,
                attempt_number=attempt_number,
                delay_seconds=delay,
            )

        if reversible and getattr(bridge_result, "rollback_token", None):
            return RecoveryDecision(
                action=RecoveryAction.ROLLBACK,
                reason="Reversible failure with rollback token",
                attempt_number=attempt_number,
            )

        if not self._policy.can_retry(attempt_number):
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason="Retry limit reached",
                attempt_number=attempt_number,
            )

        return RecoveryDecision(
            action=RecoveryAction.ABORT,
            reason="Non-retryable failure",
            attempt_number=attempt_number,
        )

    def record_attempt(
        self,
        *,
        failure_reason: str | None,
        recovery: RecoveryDecision,
    ) -> None:
        """Update in-memory recovery counters after a failed attempt."""
        self._state.current_retry = int(recovery.attempt_number)
        self._state.retry_count = max(
            self._state.retry_count, int(recovery.attempt_number)
        )
        self._state.last_failure_reason = failure_reason
        self._state.last_recovery_action = recovery.action
        self._policy.attempt_number = int(recovery.attempt_number)
        self._policy.retry_reason = recovery.retry_reason or failure_reason
        self._state.policy = self._policy

    def store_rollback(self, record: RollbackRecord | None) -> None:
        """Store rollback info when a tool reports reversible execution."""
        if record is None or not record.reversible:
            self._state.rollback_available = False
            if record is not None and not record.reversible:
                # Explicitly irreversible — never mark available.
                self._state.rollback = RollbackRecord(
                    rollback_status=RollbackStatus.SKIPPED,
                    rollback_reason="Tool reported irreversible execution",
                    reversible=False,
                )
            return
        self._state.rollback = record
        self._state.rollback_available = (
            record.rollback_status == RollbackStatus.AVAILABLE
            and not record.rollback_completed
        )

    def rollback(
        self,
        *,
        reason: str | None = None,
        rollback_fn: Any | None = None,
    ) -> RollbackRecord:
        """Execute rollback when available; never for irreversible records."""
        record = self._state.rollback
        if record is None or not record.reversible:
            skipped = RollbackRecord(
                rollback_status=RollbackStatus.SKIPPED,
                rollback_reason=reason
                or "Rollback refused — irreversible or unavailable",
                reversible=False,
                rollback_completed=False,
            )
            logger.info(
                "%s status=%s reason=%s",
                DIAG_EXECUTION_ROLLBACK,
                skipped.rollback_status.value,
                skipped.rollback_reason,
            )
            self._state.rollback = skipped
            self._state.rollback_available = False
            return skipped

        record.rollback_status = RollbackStatus.IN_PROGRESS
        record.rollback_reason = reason or record.rollback_reason or "Rollback requested"
        try:
            if rollback_fn is not None:
                rollback_fn(record)
            record.rollback_status = RollbackStatus.COMPLETED
            record.rollback_completed = True
            self._state.rollback_available = False
            logger.info(
                "%s status=%s rollback_id=%s tool_id=%s",
                DIAG_EXECUTION_ROLLBACK,
                record.rollback_status.value,
                record.rollback_id,
                record.tool_id,
            )
        except Exception as exc:
            record.rollback_status = RollbackStatus.FAILED
            record.rollback_completed = False
            record.rollback_reason = f"Rollback failed: {exc}"
            logger.info(
                "%s status=%s reason=%s",
                DIAG_EXECUTION_ROLLBACK,
                record.rollback_status.value,
                record.rollback_reason,
            )
        self._state.rollback = record
        return record

    def mark_recovered(self, *, reason: str | None = None) -> None:
        self._state.execution_recovered = True
        logger.info(
            "%s reason=%s retry_count=%s",
            DIAG_EXECUTION_RECOVERED,
            reason or "recovered",
            self._state.retry_count,
        )

    def sleep_before_retry(self, decision: RecoveryDecision) -> None:
        delay = max(0.0, float(decision.delay_seconds))
        if delay > 0:
            self._sleep(delay)

    def fingerprint_action(
        self,
        *,
        action: str | None,
        tool_id: str | None = None,
        action_id: str | None = None,
        decision_id: str | None = None,
    ) -> str:
        parts = [
            str(tool_id or ""),
            str(action_id or ""),
            str(action or ""),
            str(decision_id or ""),
        ]
        return "|".join(parts)

    def register_irreversible_executed(self, fingerprint: str) -> None:
        if fingerprint:
            self._irreversible_executed.add(fingerprint)

    def is_irreversible_already_executed(self, fingerprint: str) -> bool:
        return bool(fingerprint) and fingerprint in self._irreversible_executed

    def persist_checkpoint(self, checkpoint: ExecutionCheckpoint) -> None:
        """Write a single lightweight checkpoint (no duplicated persistence)."""
        self._checkpoint = checkpoint
        if self._checkpoint_path is None:
            return
        payload = {"checkpoint": checkpoint.to_dict()}
        try:
            self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with self._checkpoint_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
        except OSError as exc:
            # Keep in-memory checkpoint; degrade gracefully on lock/permission errors.
            logger.warning("Failed to persist execution checkpoint: %s", exc)

    def load_checkpoint(self) -> ExecutionCheckpoint | None:
        if self._checkpoint is not None:
            return self._checkpoint
        if self._checkpoint_path is None or not self._checkpoint_path.exists():
            return None
        try:
            with self._checkpoint_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load execution checkpoint: %s", exc)
            return None
        data = raw.get("checkpoint") if isinstance(raw, Mapping) else None
        checkpoint = ExecutionCheckpoint.from_dict(
            data if isinstance(data, Mapping) else raw
        )
        self._checkpoint = checkpoint
        return checkpoint

    def clear_checkpoint(self) -> None:
        self._checkpoint = None
        if self._checkpoint_path is None:
            return
        try:
            if self._checkpoint_path.exists():
                self._checkpoint_path.unlink()
        except OSError as exc:
            logger.warning("Failed to clear execution checkpoint: %s", exc)

    def apply_workspace_update(self, workspace: Any | None) -> None:
        """Mirror recovery fields onto request-scoped WorkspaceState."""
        if workspace is None:
            return
        state = self._state
        if hasattr(workspace, "current_retry"):
            workspace.current_retry = state.current_retry
        if hasattr(workspace, "retry_count"):
            workspace.retry_count = state.retry_count
        if hasattr(workspace, "rollback_available"):
            workspace.rollback_available = state.rollback_available
        if hasattr(workspace, "execution_recovered"):
            workspace.execution_recovered = state.execution_recovered
        if hasattr(workspace, "last_failure_reason"):
            workspace.last_failure_reason = state.last_failure_reason


def _failure_text(
    bridge_result: BridgeExecutionResult | None,
    status: ExecutionStatus,
) -> str | None:
    if bridge_result is not None:
        return (
            bridge_result.error
            or bridge_result.blocked_reason
            or bridge_result.message
            or status.value
        )
    return status.value


def _is_retryable_text(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _RETRYABLE_MARKERS)


def _parse_recovery_action(value: Any) -> RecoveryAction | None:
    if isinstance(value, RecoveryAction):
        return value
    text = str(value or "").strip().upper()
    if not text:
        return None
    try:
        return RecoveryAction(text)
    except ValueError:
        aliases = {
            "RETRY": RecoveryAction.RETRY,
            "ROLLBACK": RecoveryAction.ROLLBACK,
            "ABORT": RecoveryAction.ABORT,
            "WAIT": RecoveryAction.WAIT,
            "REQUEST_USER": RecoveryAction.REQUEST_USER,
            "ASK_USER": RecoveryAction.REQUEST_USER,
            "PARTIAL": RecoveryAction.MARK_PARTIAL_SUCCESS,
            "MARK_PARTIAL_SUCCESS": RecoveryAction.MARK_PARTIAL_SUCCESS,
            "PARTIAL_SUCCESS": RecoveryAction.MARK_PARTIAL_SUCCESS,
        }
        return aliases.get(text)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

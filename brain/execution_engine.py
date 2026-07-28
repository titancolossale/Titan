# =====================================
# Titan Execution Engine
# =====================================

"""Transform Decision selections into executable tasks (Phase 18.1–18.4).

Flow:
    Decision → ExecutionTask → safety evaluation →
    APPROVED | CONFIRMATION_REQUIRED | BLOCKED | FORBIDDEN →
    Tool Execution Bridge → Tool Registry → Tool Adapter →
    Recovery (retry / rollback / abort / wait / ask user) →
    ExecutionResult → WorkspaceState → DecisionEngine feedback

Reuses DecisionEngine, PlanningEngine Plan, Goal / Project / Mission,
request-scoped WorkspaceState, AutonomyPolicy, ConfirmationGate,
Tool Registry, and PermissionManager. Does not recreate those systems.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from brain.autonomy_policy import AutonomyPolicy
from brain.execution_models import (
    ExecutionContext,
    ExecutionHistory,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
)
from brain.execution_recovery import (
    DIAG_EXECUTION_ABORT,
    DIAG_EXECUTION_RESUME,
    DIAG_EXECUTION_RETRY,
    DIAG_EXECUTION_TIMEOUT,
    ExecutionCheckpoint,
    ExecutionRecoveryManager,
    ExecutionRetryPolicy,
    RecoveryAction,
    RecoveryDecision,
    RollbackRecord,
    RollbackStatus,
    utc_now_iso,
)
from brain.execution_safety import (
    ExecutionRiskLevel,
    ExecutionSafetyEvaluator,
    ExecutionSafetyResult,
    PendingExecutionConfirmation,
    SafetyDecision,
    sanitize_public_metadata,
)
from brain.execution_tool_bridge import ToolExecutionBridge
from brain.execution_tool_models import BridgeExecutionResult, BridgeExecutionStatus
from brain.planning_models import Plan
from config.settings import (
    EXECUTION_CHECKPOINT_PATH,
    EXECUTION_RETRY_BACKOFF_MULTIPLIER,
    EXECUTION_RETRY_DELAY,
    EXECUTION_RETRY_MAX_ATTEMPTS,
    EXECUTION_RETRY_ON_TIMEOUT,
    EXECUTION_TIMEOUT_SECONDS,
    TITAN_TOOL_CONFIRMATION_TTL_SECONDS,
)
from tools.confirmation_gate import ConfirmationGate
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_run_models import ToolExecutionContext

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 50

# Synthetic capability name registered with ConfirmationGate for TTL / lookup
# compatibility — not a real external tool.
_EXECUTION_GATE_TOOL = "__execution__"

_BRIDGE_STATUS_MAP = {
    BridgeExecutionStatus.SUCCESS: ExecutionStatus.COMPLETED,
    BridgeExecutionStatus.PARTIAL_SUCCESS: ExecutionStatus.PARTIAL_SUCCESS,
    BridgeExecutionStatus.FAILED: ExecutionStatus.FAILED,
    BridgeExecutionStatus.BLOCKED: ExecutionStatus.BLOCKED,
    BridgeExecutionStatus.FORBIDDEN: ExecutionStatus.FORBIDDEN,
    BridgeExecutionStatus.TIMEOUT: ExecutionStatus.TIMEOUT,
    BridgeExecutionStatus.CANCELLED: ExecutionStatus.CANCELLED,
}


class ExecutionEngine:
    """Create and run next-action ExecutionTasks from Decision selections."""

    def __init__(
        self,
        *,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        safety_evaluator: ExecutionSafetyEvaluator | None = None,
        confirmation_gate: ConfirmationGate | None = None,
        autonomy_policy: AutonomyPolicy | None = None,
        tool_bridge: ToolExecutionBridge | None = None,
        recovery_manager: ExecutionRecoveryManager | None = None,
        retry_policy: ExecutionRetryPolicy | None = None,
        checkpoint_path: str | Path | None = None,
        timeout_seconds: float | None = None,
        auto_resume: bool = False,
    ) -> None:
        self._active_task: ExecutionTask | None = None
        self._active_result: ExecutionResult | None = None
        self._active_context: ExecutionContext | None = None
        self._history = ExecutionHistory(limit=max(1, int(history_limit)))
        self._safety = safety_evaluator or ExecutionSafetyEvaluator(
            autonomy_policy=autonomy_policy
        )
        self._confirmation_gate = confirmation_gate or ConfirmationGate(
            autonomy_policy=autonomy_policy or self._safety.autonomy_policy,
            token_ttl_seconds=TITAN_TOOL_CONFIRMATION_TTL_SECONDS,
        )
        self._tool_bridge = tool_bridge or ToolExecutionBridge(
            confirmation_gate=self._confirmation_gate,
            default_timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else EXECUTION_TIMEOUT_SECONDS
            ),
        )
        policy = retry_policy or ExecutionRetryPolicy(
            max_attempts=EXECUTION_RETRY_MAX_ATTEMPTS,
            retry_delay=EXECUTION_RETRY_DELAY,
            backoff_multiplier=EXECUTION_RETRY_BACKOFF_MULTIPLIER,
            retry_on_timeout=EXECUTION_RETRY_ON_TIMEOUT,
        )
        self._recovery = recovery_manager or ExecutionRecoveryManager(
            policy=policy,
            checkpoint_path=(
                checkpoint_path
                if checkpoint_path is not None
                else EXECUTION_CHECKPOINT_PATH
            ),
        )
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else EXECUTION_TIMEOUT_SECONDS
        )
        self._pending: dict[str, PendingExecutionConfirmation] = {}
        self._executed_confirmation_ids: set[str] = set()
        self._lock = threading.RLock()
        self._last_action_metadata: Mapping[str, Any] | None = None
        self._last_session_id: str = "default"
        self._last_user: str = "Nolan"
        self._last_turn_id: str | None = None
        self._last_confirmation_token: str | None = None
        if auto_resume:
            self.resume_after_restart(workspace=None, send_feedback=False)

    @property
    def active_task(self) -> ExecutionTask | None:
        return self._active_task

    @property
    def active_result(self) -> ExecutionResult | None:
        return self._active_result

    @property
    def active_context(self) -> ExecutionContext | None:
        return self._active_context

    @property
    def history(self) -> ExecutionHistory:
        return self._history

    @property
    def safety_evaluator(self) -> ExecutionSafetyEvaluator:
        return self._safety

    @property
    def confirmation_gate(self) -> ConfirmationGate:
        return self._confirmation_gate

    @property
    def tool_bridge(self) -> ToolExecutionBridge:
        return self._tool_bridge

    @property
    def recovery_manager(self) -> ExecutionRecoveryManager:
        return self._recovery

    def execute(
        self,
        *,
        decision: Any | None = None,
        plan: Plan | None = None,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = True,
        now: datetime | None = None,
        capability: Any | None = None,
        action_metadata: Mapping[str, Any] | None = None,
        execution_mode: str | None = None,
        confirmation_token: str | None = None,
        session_id: str = "default",
        user: str = "Nolan",
        turn_id: str | None = None,
    ) -> ExecutionResult:
        """Run the full Decision → safety → ExecutionResult flow once.

        Safety evaluation always runs before any side-effecting work.
        """
        # Confirmation resume path — never create a parallel task.
        if confirmation_token:
            return self.confirm(
                confirmation_token,
                workspace=workspace,
                decision_feedback=decision_feedback,
                send_feedback=send_feedback,
                now=now,
                session_id=session_id,
                user=user,
                turn_id=turn_id,
            )

        stamp = now or datetime.now(timezone.utc)
        started = time.perf_counter()
        self.purge_expired_confirmations()
        self._last_action_metadata = dict(action_metadata or {}) if action_metadata else None
        self._last_session_id = session_id
        self._last_user = user
        self._last_turn_id = turn_id
        self._last_confirmation_token = confirmation_token

        # One shared ExecutionContext for this pass — no duplicated objects.
        context = ExecutionContext.build(
            decision=decision,
            plan=plan,
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
        )
        self._active_context = context

        action = getattr(decision, "selected_action", None) if decision else None
        decision_id = getattr(decision, "decision_id", None) if decision else None

        task = ExecutionTask(
            task_id=self._reuse_or_new_task_id(action, decision_id),
            action=action,
            status=ExecutionStatus.PENDING,
            context=context,
            created_at=stamp,
            updated_at=stamp,
            decision_id=decision_id,
        )
        self._active_task = task
        logger.info(
            "EXECUTION_CREATED task_id=%s action=%s decision_id=%s status=%s",
            task.task_id,
            task.action,
            task.decision_id,
            task.status.value,
        )

        block_reason = self._validate_prerequisites(decision=decision, plan=plan)
        if block_reason is not None:
            result = self._finalize_blocked(
                task,
                reason=block_reason,
                started=started,
                now=stamp,
            )
            self._apply_workspace_update(workspace, task, result)
            self._maybe_feedback(decision_feedback, result, decision, send_feedback)
            return result

        if not action:
            result = self._finalize_cancelled(
                task,
                reason=self._empty_reason(decision, plan),
                started=started,
                now=stamp,
            )
            self._apply_workspace_update(workspace, task, result)
            self._maybe_feedback(decision_feedback, result, decision, send_feedback)
            return result

        # --- Phase 18.2: safety before any side effect ---
        safety = self._safety.evaluate(
            task_id=task.task_id,
            action=action,
            capability=capability,
            action_metadata=action_metadata,
            decision=decision,
            execution_mode=execution_mode,
            now=stamp,
            issue_confirmation_id=True,
        )
        task.safety = safety
        task.risk_level = safety.risk_level.value
        self._log_safety_evaluated(safety)

        if safety.decision == SafetyDecision.FORBIDDEN:
            result = self._finalize_forbidden(
                task,
                safety=safety,
                started=started,
                now=stamp,
            )
            self._apply_workspace_update(workspace, task, result)
            self._maybe_feedback(decision_feedback, result, decision, send_feedback)
            return result

        if safety.decision == SafetyDecision.BLOCKED:
            result = self._finalize_blocked(
                task,
                reason=safety.reason,
                started=started,
                now=stamp,
                safety=safety,
            )
            self._apply_workspace_update(workspace, task, result)
            self._maybe_feedback(decision_feedback, result, decision, send_feedback)
            return result

        if safety.decision == SafetyDecision.CONFIRMATION_REQUIRED:
            result = self._hold_for_confirmation(
                task,
                safety=safety,
                started=started,
                now=stamp,
                session_id=session_id,
                user=user,
                turn_id=turn_id or task.task_id,
                action_metadata=action_metadata,
            )
            self._apply_workspace_update(workspace, task, result)
            # No Decision feedback until the action actually runs or is rejected.
            return result

        return self._run_approved_task(
            task,
            workspace=workspace,
            decision=decision,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            started=started,
            now=now,
        )

    def confirm(
        self,
        confirmation_id: str,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = True,
        now: datetime | None = None,
        session_id: str = "default",
        user: str = "Nolan",
        turn_id: str | None = None,
    ) -> ExecutionResult:
        """Approve a pending confirmation and execute at most once."""
        stamp = now or datetime.now(timezone.utc)
        started = time.perf_counter()
        token = str(confirmation_id or "").strip()
        self._last_session_id = session_id
        self._last_user = user
        self._last_turn_id = turn_id
        self._last_confirmation_token = token

        with self._lock:
            self.purge_expired_confirmations()
            if token in self._executed_confirmation_ids:
                logger.info(
                    "EXECUTION_CONFIRMED task_id=%s confirmation_id=%s "
                    "duplicate=true skipped=true",
                    getattr(self._active_task, "task_id", None),
                    token,
                )
                if self._active_result is not None:
                    return self._active_result
                return self._duplicate_confirm_result(token, stamp)

            pending = self._pending.get(token)
            if pending is None:
                gate_pending = self._confirmation_gate.lookup_pending(token)
                if gate_pending is None or gate_pending.tool_name != _EXECUTION_GATE_TOOL:
                    logger.info(
                        "EXECUTION_CONFIRMATION_EXPIRED confirmation_id=%s",
                        token,
                    )
                    return self._expired_confirm_result(token, stamp)
                # Reconstruct from gate record when engine pending was lost.
                pending = PendingExecutionConfirmation(
                    confirmation_id=token,
                    task_id=str(gate_pending.params.get("task_id") or ""),
                    action=str(gate_pending.params.get("action") or "") or None,
                    risk_level=ExecutionRiskLevel.HIGH_RISK_WRITE,
                    expected_impact="Confirmed execution",
                    created_at=time.monotonic(),
                )
                self._pending[token] = pending

            if pending.executed or pending.rejected:
                logger.info(
                    "EXECUTION_CONFIRMED task_id=%s confirmation_id=%s "
                    "duplicate=true skipped=true",
                    pending.task_id,
                    token,
                )
                if self._active_result is not None:
                    return self._active_result
                return self._duplicate_confirm_result(token, stamp)

            task = self._active_task
            if task is None or (
                pending is not None and task.task_id != pending.task_id
            ):
                logger.info(
                    "EXECUTION_CONFIRMATION_EXPIRED confirmation_id=%s "
                    "reason=task_missing",
                    token,
                )
                self._pending.pop(token, None)
                return self._expired_confirm_result(token, stamp)

            if task.status not in (
                ExecutionStatus.AWAITING_CONFIRMATION,
                ExecutionStatus.PENDING,
            ):
                logger.info(
                    "EXECUTION_CONFIRMED task_id=%s confirmation_id=%s "
                    "duplicate=true status=%s skipped=true",
                    task.task_id,
                    token,
                    task.status.value,
                )
                if self._active_result is not None:
                    return self._active_result
                return self._duplicate_confirm_result(token, stamp)

            # Bind params for ConfirmationGate validation (public fields only).
            params = {
                "task_id": task.task_id,
                "action": task.action or "",
            }
            ctx = ToolExecutionContext(
                caller="execution_engine",
                user=user,
                session_id=session_id,
                turn_id=turn_id or task.task_id,
                confirmed=True,
                confirmation_token=token,
                execution_mode=ExecutionMode.LIVE,
            )
            valid = self._confirmation_gate.validate_confirmation(
                ctx,
                _EXECUTION_GATE_TOOL,
                params,
            )
            if not valid:
                # Token expired or mismatch — never execute.
                self._pending.pop(token, None)
                task.status = ExecutionStatus.CANCELLED
                task.error = "Confirmation expired or invalid"
                task.completed_at = stamp
                task.updated_at = stamp
                logger.info(
                    "EXECUTION_CONFIRMATION_EXPIRED task_id=%s confirmation_id=%s",
                    task.task_id,
                    token,
                )
                result = ExecutionResult.from_task(
                    task,
                    message="Confirmation expired or invalid",
                    success=False,
                    actual_result=0.0,
                    duration=max(0.0, time.perf_counter() - started),
                    now=stamp,
                )
                self._history.append(result)
                self._active_result = result
                self._apply_workspace_update(workspace, task, result)
                return result

            # Claim execution slot under the lock — at most once.
            if pending is not None:
                pending.executed = True
            self._executed_confirmation_ids.add(token)
            self._pending.pop(token, None)

            logger.info(
                "EXECUTION_CONFIRMED task_id=%s confirmation_id=%s action=%s",
                task.task_id,
                token,
                task.action,
            )

        return self._run_approved_task(
            task,
            workspace=workspace,
            decision=getattr(task.context, "decision", None),
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            started=started,
            now=now,
        )

    def reject(
        self,
        confirmation_id: str,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = True,
        now: datetime | None = None,
        reason: str = "User rejected confirmation",
    ) -> ExecutionResult:
        """Reject a pending confirmation — task never executes."""
        stamp = now or datetime.now(timezone.utc)
        started = time.perf_counter()
        token = str(confirmation_id or "").strip()

        with self._lock:
            pending = self._pending.get(token)
            task = self._active_task
            if pending is None or task is None or task.task_id != pending.task_id:
                logger.info(
                    "EXECUTION_REJECTED confirmation_id=%s reason=not_found",
                    token,
                )
                return self._expired_confirm_result(token, stamp, rejected=True)

            if pending.executed or pending.rejected:
                if self._active_result is not None:
                    return self._active_result

            pending.rejected = True
            self._pending.pop(token, None)
            # Drop matching ConfirmationGate record if still present.
            self._confirmation_gate._pending.pop(token, None)  # noqa: SLF001

            task.status = ExecutionStatus.CANCELLED
            task.error = reason
            task.blocked_reason = reason
            task.completed_at = stamp
            task.updated_at = stamp
            logger.info(
                "EXECUTION_REJECTED task_id=%s confirmation_id=%s action=%s",
                task.task_id,
                token,
                task.action,
            )
            result = ExecutionResult.from_task(
                task,
                message=reason,
                success=False,
                actual_result=0.0,
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self._history.append(result)
            self._active_result = result

        self._apply_workspace_update(workspace, task, result)
        decision = getattr(task.context, "decision", None) if task else None
        self._maybe_feedback(decision_feedback, result, decision, send_feedback)
        return result

    def lookup_pending(self, confirmation_id: str) -> PendingExecutionConfirmation | None:
        """Return pending confirmation metadata without consuming the token."""
        with self._lock:
            self.purge_expired_confirmations()
            return self._pending.get(str(confirmation_id or "").strip())

    def purge_expired_confirmations(self) -> int:
        """Expire pending confirmations past TTL; return count removed."""
        removed = 0
        now = time.monotonic()
        ttl = self._safety.confirmation_ttl_seconds
        with self._lock:
            expired = [
                token
                for token, pending in self._pending.items()
                if now - pending.created_at > ttl and not pending.executed
            ]
            for token in expired:
                pending = self._pending.pop(token, None)
                removed += 1
                logger.info(
                    "EXECUTION_CONFIRMATION_EXPIRED task_id=%s confirmation_id=%s",
                    getattr(pending, "task_id", None),
                    token,
                )
                task = self._active_task
                if (
                    task is not None
                    and pending is not None
                    and task.task_id == pending.task_id
                    and task.status == ExecutionStatus.AWAITING_CONFIRMATION
                ):
                    task.status = ExecutionStatus.CANCELLED
                    task.error = "Confirmation expired"
                    task.updated_at = datetime.now(timezone.utc)
            # Keep ConfirmationGate in sync.
            self._confirmation_gate.purge_expired()
        return removed

    def _hold_for_confirmation(
        self,
        task: ExecutionTask,
        *,
        safety: ExecutionSafetyResult,
        started: float,
        now: datetime,
        session_id: str,
        user: str,
        turn_id: str,
        action_metadata: Mapping[str, Any] | None,
    ) -> ExecutionResult:
        confirmation_id = safety.confirmation_id or str(uuid.uuid4())
        task.status = ExecutionStatus.AWAITING_CONFIRMATION
        task.confirmation_id = confirmation_id
        task.updated_at = now
        task.blocked_reason = None

        # Rebuild safety with stable confirmation_id for prompt / state.
        held = ExecutionSafetyResult(
            task_id=safety.task_id,
            risk_level=safety.risk_level,
            decision=safety.decision,
            reason=safety.reason,
            requires_confirmation=True,
            confirmation_id=confirmation_id,
            reversible=safety.reversible,
            expected_impact=safety.expected_impact,
            evaluated_at=safety.evaluated_at,
            action=safety.action,
        )
        task.safety = held

        public_meta = sanitize_public_metadata(action_metadata)
        pending = PendingExecutionConfirmation(
            confirmation_id=confirmation_id,
            task_id=task.task_id,
            action=task.action,
            risk_level=safety.risk_level,
            expected_impact=safety.expected_impact,
            created_at=time.monotonic(),
            decision_id=task.decision_id,
            public_metadata=public_meta,
        )
        with self._lock:
            self._pending[confirmation_id] = pending

        # Register with existing ConfirmationGate for shared TTL / token lookup.
        capability = ToolCapability(
            name=_EXECUTION_GATE_TOOL,
            description="Cognitive execution confirmation",
            parameters=(),
            risk_level=self._map_gate_risk(safety.risk_level),
            requires_confirmation=True,
        )
        gate_ctx = ToolExecutionContext(
            caller="execution_engine",
            user=user,
            session_id=session_id,
            turn_id=turn_id,
            execution_mode=ExecutionMode.LIVE,
        )
        # Public params only — never sensitive tool arguments.
        self._confirmation_gate.issue_request(
            _EXECUTION_GATE_TOOL,
            capability,
            gate_ctx,
            {"task_id": task.task_id, "action": task.action or ""},
        )
        # Align token: ConfirmationGate generates its own UUID. Replace our
        # pending key with the gate-issued token so /confirm works end-to-end.
        gate_token = self._align_confirmation_token(confirmation_id, task)

        duration = max(0.0, time.perf_counter() - started)
        result = ExecutionResult.from_task(
            task,
            message=(
                f"Confirmation required ({task.risk_level}): {safety.reason}. "
                f"Impact: {safety.expected_impact}"
            ),
            success=False,
            actual_result=0.0,
            duration=duration,
            now=now,
        )
        # Awaiting confirmation is not a terminal history entry for learning,
        # but keep active_result for callers / UI.
        self._active_result = result
        logger.info(
            "EXECUTION_CONFIRMATION_REQUIRED task_id=%s action=%s "
            "risk_level=%s confirmation_id=%s",
            task.task_id,
            task.action,
            task.risk_level,
            gate_token or task.confirmation_id,
        )
        return result

    def _align_confirmation_token(
        self,
        provisional_id: str,
        task: ExecutionTask,
    ) -> str | None:
        """Use ConfirmationGate-issued token as the public confirmation_id."""
        with self._lock:
            gate_pending = self._confirmation_gate._pending  # noqa: SLF001
            match_token = None
            for token, record in gate_pending.items():
                if (
                    record.tool_name == _EXECUTION_GATE_TOOL
                    and record.params.get("task_id") == task.task_id
                ):
                    match_token = token
                    break
            if match_token is None:
                return provisional_id

            pending = self._pending.pop(provisional_id, None)
            if pending is None:
                return match_token
            pending.confirmation_id = match_token
            self._pending[match_token] = pending
            task.confirmation_id = match_token
            if task.safety is not None:
                task.safety = ExecutionSafetyResult(
                    task_id=task.safety.task_id,
                    risk_level=task.safety.risk_level,
                    decision=task.safety.decision,
                    reason=task.safety.reason,
                    requires_confirmation=True,
                    confirmation_id=match_token,
                    reversible=task.safety.reversible,
                    expected_impact=task.safety.expected_impact,
                    evaluated_at=task.safety.evaluated_at,
                    action=task.safety.action,
                )
            return match_token

    def _run_approved_task(
        self,
        task: ExecutionTask,
        *,
        workspace: Any | None,
        decision: Any | None,
        decision_feedback: Callable[..., Any] | None,
        send_feedback: bool,
        started: float,
        now: datetime | None,
    ) -> ExecutionResult:
        stamp = now or datetime.now(timezone.utc)
        task.status = ExecutionStatus.RUNNING
        task.started_at = stamp
        task.updated_at = stamp
        self._recovery.reset_for_task()
        logger.info(
            "EXECUTION_STARTED task_id=%s action=%s status=%s",
            task.task_id,
            task.action,
            task.status.value,
        )

        # Irreversible re-execution guard — never run the same irreversible
        # action twice (Phase 18.4 safety).
        fingerprint = self._action_fingerprint(task)
        safety = task.safety
        irreversible = safety is not None and not bool(getattr(safety, "reversible", True))
        if irreversible and self._recovery.is_irreversible_already_executed(fingerprint):
            logger.info(
                "%s task_id=%s reason=irreversible_already_executed",
                DIAG_EXECUTION_ABORT,
                task.task_id,
            )
            task.status = ExecutionStatus.FAILED
            task.error = "Irreversible action already executed — refusing duplicate run"
            task.completed_at = stamp
            task.updated_at = stamp
            task.recovery_action = RecoveryAction.ABORT.value
            task.recovery = self._recovery.state
            result = ExecutionResult.from_task(
                task,
                message=task.error,
                success=False,
                actual_result=0.0,
                duration=max(0.0, time.perf_counter() - started),
                now=stamp,
            )
            self._history.append(result)
            self._active_result = result
            self._recovery.clear_checkpoint()
            self._apply_workspace_update(workspace, task, result)
            self._maybe_feedback(decision_feedback, result, decision, send_feedback)
            return result

        self._persist_running_checkpoint(task, attempt=0)
        attempt = 0
        bridge_result: BridgeExecutionResult | None = None
        result: ExecutionResult | None = None

        while True:
            attempt += 1
            task.attempt_number = attempt
            try:
                bridge_result = self._run_via_bridge(
                    task, workspace=workspace, now=now or stamp
                )
            except Exception as exc:
                duration = max(0.0, time.perf_counter() - started)
                failed_at = now or datetime.now(timezone.utc)
                bridge_result = BridgeExecutionResult.from_exception(
                    tool_id=None,
                    action_id=None,
                    exc=exc,
                    duration=duration,
                    now=failed_at,
                )

            assert bridge_result is not None
            task.bridge_result = bridge_result
            task.last_tool = bridge_result.tool_id
            mapped_status = _BRIDGE_STATUS_MAP.get(
                bridge_result.status, ExecutionStatus.FAILED
            )
            task.status = mapped_status

            # Store rollback info when the tool reports reversible execution.
            rollback_record = RollbackRecord.from_bridge_result(bridge_result)
            if rollback_record is not None:
                self._recovery.store_rollback(rollback_record)
            elif bridge_result.tool_id and not getattr(
                bridge_result, "reversible", False
            ):
                # Explicit irreversible tool outcome — never mark rollback available.
                if getattr(bridge_result, "rollback_token", None) is None and (
                    self._last_action_metadata or {}
                ).get("reversible") is False:
                    self._recovery.store_rollback(
                        RollbackRecord(
                            reversible=False,
                            rollback_status=RollbackStatus.SKIPPED,
                            rollback_reason="Tool reported irreversible execution",
                        )
                    )

            if bridge_result.status in (
                BridgeExecutionStatus.BLOCKED,
                BridgeExecutionStatus.FORBIDDEN,
            ):
                task.blocked_reason = (
                    bridge_result.blocked_reason or bridge_result.message
                )
            if bridge_result.status in (
                BridgeExecutionStatus.FAILED,
                BridgeExecutionStatus.TIMEOUT,
                BridgeExecutionStatus.CANCELLED,
            ):
                task.error = bridge_result.error or bridge_result.message

            if bridge_result.status == BridgeExecutionStatus.TIMEOUT:
                logger.info(
                    "%s task_id=%s attempt=%s error=%s",
                    DIAG_EXECUTION_TIMEOUT,
                    task.task_id,
                    attempt,
                    task.error,
                )

            # Success path — register irreversible fingerprint, clear checkpoint.
            if bridge_result.status == BridgeExecutionStatus.SUCCESS:
                if irreversible:
                    self._recovery.register_irreversible_executed(fingerprint)
                if attempt > 1:
                    self._recovery.mark_recovered(reason="retry_succeeded")
                completed_at = now or datetime.now(timezone.utc)
                task.status = ExecutionStatus.COMPLETED
                task.completed_at = completed_at
                task.updated_at = completed_at
                task.recovery = self._recovery.state
                duration = max(
                    0.0,
                    float(bridge_result.duration)
                    if bridge_result.duration > 0
                    else time.perf_counter() - started,
                )
                result = ExecutionResult.from_task(
                    task,
                    message=bridge_result.message,
                    success=True,
                    actual_result=1.0,
                    duration=duration,
                    now=completed_at,
                )
                self._history.append(result)
                self._active_result = result
                self._recovery.clear_checkpoint()
                logger.info(
                    "EXECUTION_COMPLETED task_id=%s action=%s duration=%.4f "
                    "actual_result=%s bridge_status=%s attempts=%s",
                    task.task_id,
                    task.action,
                    result.duration,
                    result.actual_result,
                    bridge_result.status.value,
                    attempt,
                )
                break

            # Classify recovery for non-success outcomes.
            recovery = self._recovery.decide(
                bridge_result=bridge_result,
                status=mapped_status,
                attempt_number=attempt,
                safety_reversible=getattr(safety, "reversible", None),
                action_metadata=self._last_action_metadata,
                was_forbidden=mapped_status == ExecutionStatus.FORBIDDEN,
                was_confirmation_failure=False,
            )
            self._recovery.record_attempt(
                failure_reason=task.error or task.blocked_reason or bridge_result.message,
                recovery=recovery,
            )
            task.recovery_action = recovery.action.value
            task.recovery = self._recovery.state

            if recovery.action == RecoveryAction.RETRY:
                logger.info(
                    "%s task_id=%s attempt=%s delay=%.4f reason=%s",
                    DIAG_EXECUTION_RETRY,
                    task.task_id,
                    attempt,
                    recovery.delay_seconds,
                    recovery.retry_reason or recovery.reason,
                )
                self._persist_running_checkpoint(task, attempt=attempt)
                self._recovery.sleep_before_retry(recovery)
                task.status = ExecutionStatus.RUNNING
                task.error = None
                continue

            if recovery.action == RecoveryAction.MARK_PARTIAL_SUCCESS:
                if irreversible:
                    self._recovery.register_irreversible_executed(fingerprint)
                completed_at = now or datetime.now(timezone.utc)
                task.status = ExecutionStatus.PARTIAL_SUCCESS
                task.completed_at = completed_at
                task.updated_at = completed_at
                task.recovery = self._recovery.state
                duration = max(
                    0.0,
                    float(bridge_result.duration)
                    if bridge_result.duration > 0
                    else time.perf_counter() - started,
                )
                result = ExecutionResult.from_task(
                    task,
                    message=bridge_result.message,
                    success=True,
                    actual_result=0.5,
                    duration=duration,
                    now=completed_at,
                )
                self._history.append(result)
                self._active_result = result
                self._recovery.clear_checkpoint()
                logger.info(
                    "EXECUTION_COMPLETED task_id=%s action=%s duration=%.4f "
                    "actual_result=%s bridge_status=PARTIAL_SUCCESS",
                    task.task_id,
                    task.action,
                    result.duration,
                    result.actual_result,
                )
                break

            if recovery.action == RecoveryAction.ROLLBACK:
                self._recovery.rollback(reason=recovery.reason)
                task.recovery = self._recovery.state
                # After rollback, abort (do not auto-re-run irreversible work).
                recovery = recovery.__class__(
                    action=RecoveryAction.ABORT,
                    reason="Rollback completed — aborting further execution",
                    attempt_number=attempt,
                )
                task.recovery_action = recovery.action.value

            if recovery.action == RecoveryAction.WAIT:
                waiting_at = now or datetime.now(timezone.utc)
                task.status = ExecutionStatus.WAITING
                task.updated_at = waiting_at
                task.error = task.error or recovery.reason
                task.recovery = self._recovery.state
                self._persist_running_checkpoint(
                    task,
                    attempt=attempt,
                    resumable=True,
                    recovery_action=RecoveryAction.WAIT.value,
                )
                duration = max(0.0, time.perf_counter() - started)
                result = ExecutionResult.from_task(
                    task,
                    message=recovery.reason,
                    success=False,
                    actual_result=0.0,
                    duration=duration,
                    now=waiting_at,
                )
                self._active_result = result
                logger.info(
                    "%s task_id=%s action=WAIT reason=%s",
                    DIAG_EXECUTION_ABORT,
                    task.task_id,
                    recovery.reason,
                )
                break

            if recovery.action == RecoveryAction.REQUEST_USER:
                # Reuse confirmation hold path semantics without re-issuing safety.
                waiting_at = now or datetime.now(timezone.utc)
                task.status = ExecutionStatus.AWAITING_CONFIRMATION
                task.updated_at = waiting_at
                task.error = None
                task.blocked_reason = recovery.reason
                task.recovery = self._recovery.state
                self._persist_running_checkpoint(
                    task,
                    attempt=attempt,
                    resumable=True,
                    recovery_action=RecoveryAction.REQUEST_USER.value,
                )
                duration = max(0.0, time.perf_counter() - started)
                result = ExecutionResult.from_task(
                    task,
                    message=recovery.reason,
                    success=False,
                    actual_result=0.0,
                    duration=duration,
                    now=waiting_at,
                )
                self._active_result = result
                break

            # ABORT (default terminal failure)
            logger.info(
                "%s task_id=%s attempt=%s reason=%s",
                DIAG_EXECUTION_ABORT,
                task.task_id,
                attempt,
                recovery.reason,
            )
            completed_at = now or datetime.now(timezone.utc)
            if task.status not in (
                ExecutionStatus.BLOCKED,
                ExecutionStatus.FORBIDDEN,
                ExecutionStatus.TIMEOUT,
                ExecutionStatus.CANCELLED,
            ):
                task.status = ExecutionStatus.FAILED
            task.completed_at = completed_at
            task.updated_at = completed_at
            task.recovery = self._recovery.state
            duration = max(
                0.0,
                float(bridge_result.duration)
                if bridge_result.duration > 0
                else time.perf_counter() - started,
            )
            result = ExecutionResult.from_task(
                task,
                message=bridge_result.message or recovery.reason,
                success=False,
                actual_result=0.0,
                duration=duration,
                now=completed_at,
            )
            self._history.append(result)
            self._active_result = result
            self._recovery.clear_checkpoint()
            logger.info(
                "EXECUTION_FAILED task_id=%s action=%s error=%s duration=%.4f "
                "bridge_status=%s attempts=%s",
                task.task_id,
                task.action,
                task.error or task.blocked_reason,
                result.duration,
                bridge_result.status.value,
                attempt,
            )
            break

        assert result is not None
        self._apply_workspace_update(workspace, task, result)
        self._maybe_feedback(decision_feedback, result, decision, send_feedback)
        return result

    def rollback(
        self,
        *,
        reason: str | None = None,
        rollback_fn: Callable[..., Any] | None = None,
        workspace: Any | None = None,
    ) -> RollbackRecord:
        """Rollback the last reversible execution when available."""
        record = self._recovery.rollback(reason=reason, rollback_fn=rollback_fn)
        task = self._active_task
        if task is not None:
            task.recovery = self._recovery.state
            task.recovery_action = RecoveryAction.ROLLBACK.value
        if workspace is not None:
            self._recovery.apply_workspace_update(workspace)
        return record

    def resume_after_restart(
        self,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = False,
        now: datetime | None = None,
    ) -> ExecutionResult | None:
        """Resume a persisted WAITING/RUNNING checkpoint, or safely abort."""
        checkpoint = self._recovery.load_checkpoint()
        if checkpoint is None:
            return None

        stamp = now or datetime.now(timezone.utc)
        logger.info(
            "%s task_id=%s status=%s resumable=%s",
            DIAG_EXECUTION_RESUME,
            checkpoint.task_id,
            checkpoint.status,
            checkpoint.resumable,
        )

        # Irreversible mid-flight — never auto-resume side effects.
        if checkpoint.irreversible_fingerprint and (
            self._recovery.is_irreversible_already_executed(
                checkpoint.irreversible_fingerprint
            )
            or checkpoint.status == ExecutionStatus.RUNNING.value
        ):
            return self._abort_checkpoint(
                checkpoint,
                reason="Interrupted irreversible execution — safely aborted",
                workspace=workspace,
                decision_feedback=decision_feedback,
                send_feedback=send_feedback,
                now=stamp,
            )

        if not checkpoint.resumable or checkpoint.status not in (
            ExecutionStatus.WAITING.value,
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.PENDING.value,
        ):
            return self._abort_checkpoint(
                checkpoint,
                reason="Checkpoint not resumable — safely aborted",
                workspace=workspace,
                decision_feedback=decision_feedback,
                send_feedback=send_feedback,
                now=stamp,
            )

        # WAIT checkpoints stay WAITING until an explicit execute resumes them.
        if checkpoint.status == ExecutionStatus.WAITING.value:
            context = ExecutionContext.build(workspace=workspace)
            task = ExecutionTask(
                task_id=checkpoint.task_id,
                action=checkpoint.action,
                status=ExecutionStatus.WAITING,
                context=context,
                created_at=stamp,
                updated_at=stamp,
                decision_id=checkpoint.decision_id,
                attempt_number=checkpoint.attempt_number,
                error=checkpoint.last_failure_reason,
                recovery_action=checkpoint.recovery_action,
                recovery=self._recovery.state,
            )
            self._active_task = task
            self._active_context = context
            self._recovery.state.last_failure_reason = checkpoint.last_failure_reason
            self._recovery.state.current_retry = checkpoint.attempt_number
            self._recovery.state.retry_count = checkpoint.attempt_number
            self._recovery.mark_recovered(reason="checkpoint_restored_waiting")
            task.recovery = self._recovery.state
            result = ExecutionResult.from_task(
                task,
                message="Execution waiting — resume available",
                success=False,
                actual_result=0.0,
                now=stamp,
            )
            self._active_result = result
            if workspace is not None:
                self._apply_workspace_update(workspace, task, result)
            return result

        # RUNNING interrupt without irreversible mark — abort safely rather than
        # replaying unknown side effects automatically.
        return self._abort_checkpoint(
            checkpoint,
            reason="Interrupted running execution — safely aborted (resume manually)",
            workspace=workspace,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=stamp,
        )

    def resume_waiting(
        self,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = True,
        now: datetime | None = None,
    ) -> ExecutionResult:
        """Continue a WAITING task through the approved execution path."""
        task = self._active_task
        if task is None or task.status != ExecutionStatus.WAITING:
            stamp = now or datetime.now(timezone.utc)
            return ExecutionResult(
                task_id=getattr(task, "task_id", str(uuid.uuid4())),
                status=ExecutionStatus.CANCELLED,
                action=getattr(task, "action", None),
                success=False,
                message="No waiting execution to resume",
                duration=0.0,
                actual_result=0.0,
                completed_at=stamp,
                error="No waiting execution to resume",
            )
        started = time.perf_counter()
        self._recovery.mark_recovered(reason="resume_waiting")
        return self._run_approved_task(
            task,
            workspace=workspace,
            decision=getattr(task.context, "decision", None),
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            started=started,
            now=now,
        )

    def _abort_checkpoint(
        self,
        checkpoint: ExecutionCheckpoint,
        *,
        reason: str,
        workspace: Any | None,
        decision_feedback: Callable[..., Any] | None,
        send_feedback: bool,
        now: datetime,
    ) -> ExecutionResult:
        context = ExecutionContext.build(workspace=workspace)
        task = ExecutionTask(
            task_id=checkpoint.task_id,
            action=checkpoint.action,
            status=ExecutionStatus.CANCELLED,
            context=context,
            created_at=now,
            updated_at=now,
            completed_at=now,
            decision_id=checkpoint.decision_id,
            attempt_number=checkpoint.attempt_number,
            error=reason,
            recovery_action=RecoveryAction.ABORT.value,
        )
        self._recovery.record_attempt(
            failure_reason=reason,
            recovery=RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason=reason,
                attempt_number=checkpoint.attempt_number,
            ),
        )
        task.recovery = self._recovery.state
        self._active_task = task
        self._active_context = context
        result = ExecutionResult.from_task(
            task,
            message=reason,
            success=False,
            actual_result=0.0,
            now=now,
        )
        self._history.append(result)
        self._active_result = result
        self._recovery.clear_checkpoint()
        logger.info(
            "%s task_id=%s reason=%s",
            DIAG_EXECUTION_ABORT,
            task.task_id,
            reason,
        )
        if workspace is not None:
            self._apply_workspace_update(workspace, task, result)
        self._maybe_feedback(
            decision_feedback,
            result,
            getattr(task.context, "decision", None),
            send_feedback,
        )
        return result

    def _persist_running_checkpoint(
        self,
        task: ExecutionTask,
        *,
        attempt: int,
        resumable: bool = True,
        recovery_action: str | None = None,
    ) -> None:
        safety = task.safety
        irreversible = safety is not None and not bool(
            getattr(safety, "reversible", True)
        )
        fingerprint = self._action_fingerprint(task) if irreversible else None
        stamp = utc_now_iso()
        checkpoint = ExecutionCheckpoint(
            task_id=task.task_id,
            action=task.action,
            status=task.status.value,
            decision_id=task.decision_id,
            attempt_number=attempt,
            last_failure_reason=task.error or task.blocked_reason,
            recovery_action=recovery_action or task.recovery_action,
            irreversible_fingerprint=fingerprint,
            rollback=(
                self._recovery.state.rollback.to_dict()
                if self._recovery.state.rollback
                else None
            ),
            created_at=stamp,
            updated_at=stamp,
            resumable=resumable,
        )
        self._recovery.persist_checkpoint(checkpoint)

    def _action_fingerprint(self, task: ExecutionTask) -> str:
        bridge = task.bridge_result
        return self._recovery.fingerprint_action(
            action=task.action,
            tool_id=getattr(bridge, "tool_id", None) if bridge else None,
            action_id=getattr(bridge, "action_id", None) if bridge else None,
            decision_id=task.decision_id,
        )

    def _run_via_bridge(
        self,
        task: ExecutionTask,
        *,
        workspace: Any | None,
        now: datetime | None = None,
    ) -> BridgeExecutionResult:
        """Dispatch through the Tool Execution Bridge (Phase 18.3).

        Every approved execution passes through the bridge — never call tools
        directly from the ExecutionEngine.
        """
        action = task.action or "None"
        goal = task.context.current_goal or "None"
        project = task.context.current_project or "None"
        mission = task.context.current_mission or "None"
        cognitive_message = (
            f"Execution ready for action={action} "
            f"goal={goal} project={project} mission={mission}"
        )
        return self._tool_bridge.dispatch(
            action=task.action,
            workspace=workspace,
            action_metadata=self._last_action_metadata,
            confirmed=True,
            confirmation_token=self._last_confirmation_token,
            session_id=self._last_session_id,
            user=self._last_user,
            turn_id=self._last_turn_id,
            timeout_seconds=self._timeout_seconds,
            now=now,
            cognitive_message=cognitive_message,
            preauthorized=True,
        )

    def _reuse_or_new_task_id(
        self,
        action: str | None,
        decision_id: str | None,
    ) -> str:
        """Reuse active task_id when the same decision action is re-executed."""
        previous = self._active_task
        if (
            previous is not None
            and previous.action == action
            and previous.decision_id == decision_id
            and action is not None
            and previous.status
            not in (
                ExecutionStatus.AWAITING_CONFIRMATION,
            )
        ):
            return previous.task_id
        return str(uuid.uuid4())

    def _validate_prerequisites(
        self,
        *,
        decision: Any | None,
        plan: Plan | None,
    ) -> str | None:
        """Return a block reason when prerequisites fail; otherwise None."""
        if plan is not None and getattr(plan, "is_blocked", False):
            reason = getattr(plan, "blocked_reason", None) or "Plan is blocked"
            return str(reason)
        if plan is not None:
            status = getattr(plan, "status", None)
            status_value = getattr(status, "value", status)
            if status_value == "BLOCKED":
                return str(
                    getattr(plan, "blocked_reason", None) or "Plan is blocked"
                )
            if status_value == "COMPLETED":
                return "Plan is completed — no executable actions"
        if decision is not None:
            reason = str(getattr(decision, "reason", "") or "").lower()
            if getattr(decision, "selected_action", None) is None and "blocked" in reason:
                return str(getattr(decision, "reason", None) or "Decision blocked")
        return None

    def _empty_reason(self, decision: Any | None, plan: Plan | None) -> str:
        if decision is not None and getattr(decision, "reason", None):
            return str(decision.reason)
        if plan is not None and getattr(plan, "is_completed", False):
            return "Plan completed — nothing to execute"
        return "No selected action to execute"

    def _finalize_forbidden(
        self,
        task: ExecutionTask,
        *,
        safety: ExecutionSafetyResult,
        started: float,
        now: datetime,
    ) -> ExecutionResult:
        task.status = ExecutionStatus.FORBIDDEN
        task.blocked_reason = safety.reason
        task.completed_at = now
        task.updated_at = now
        duration = max(0.0, time.perf_counter() - started)
        result = ExecutionResult.from_task(
            task,
            message=f"Execution forbidden: {safety.reason}",
            success=False,
            actual_result=0.0,
            duration=duration,
            now=now,
        )
        self._history.append(result)
        self._active_result = result
        logger.info(
            "EXECUTION_FORBIDDEN task_id=%s action=%s reason=%s",
            task.task_id,
            task.action,
            safety.reason,
        )
        return result

    def _finalize_blocked(
        self,
        task: ExecutionTask,
        *,
        reason: str,
        started: float,
        now: datetime,
        safety: ExecutionSafetyResult | None = None,
    ) -> ExecutionResult:
        task.status = ExecutionStatus.BLOCKED
        task.blocked_reason = reason
        if safety is not None:
            task.safety = safety
            task.risk_level = safety.risk_level.value
        task.completed_at = now
        task.updated_at = now
        duration = max(0.0, time.perf_counter() - started)
        result = ExecutionResult.from_task(
            task,
            message=f"Execution blocked: {reason}",
            success=False,
            actual_result=0.0,
            duration=duration,
            now=now,
        )
        self._history.append(result)
        self._active_result = result
        logger.info(
            "EXECUTION_BLOCKED task_id=%s action=%s reason=%s",
            task.task_id,
            task.action,
            reason,
        )
        # Keep legacy diagnostic name for Phase 18.1 compatibility.
        logger.info(
            "EXECUTION_FAILED task_id=%s action=%s status=BLOCKED reason=%s",
            task.task_id,
            task.action,
            reason,
        )
        return result

    def _finalize_cancelled(
        self,
        task: ExecutionTask,
        *,
        reason: str,
        started: float,
        now: datetime,
    ) -> ExecutionResult:
        task.status = ExecutionStatus.CANCELLED
        task.error = reason
        task.completed_at = now
        task.updated_at = now
        duration = max(0.0, time.perf_counter() - started)
        result = ExecutionResult.from_task(
            task,
            message=reason,
            success=False,
            actual_result=0.0,
            duration=duration,
            now=now,
        )
        self._history.append(result)
        self._active_result = result
        logger.info(
            "EXECUTION_FAILED task_id=%s action=%s status=CANCELLED reason=%s",
            task.task_id,
            task.action,
            reason,
        )
        return result

    def _apply_workspace_update(
        self,
        workspace: Any | None,
        task: ExecutionTask,
        result: ExecutionResult,
    ) -> None:
        """Mirror execution onto request-scoped WorkspaceState (in-place).

        Updates ``next_action``, ``current_focus``, ``running_tasks``, and
        Phase 18.2 safety fields. Does not overwrite ``current_step`` when
        already set — StateEvolution / MissionManager own that field.
        Never writes secrets or raw tool arguments into workspace.
        """
        if workspace is None:
            return

        action = task.action
        if result.status == ExecutionStatus.RUNNING:
            workspace.next_action = action
            workspace.current_focus = action
            if action and not getattr(workspace, "current_step", None):
                workspace.current_step = action
            workspace.running_tasks = [action] if action else []
            workspace.brain_mode = "working"
        elif result.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.PARTIAL_SUCCESS,
        ):
            workspace.next_action = action
            workspace.current_focus = action
            if action and not getattr(workspace, "current_step", None):
                workspace.current_step = action
            workspace.running_tasks = []
            if getattr(workspace, "brain_mode", None) in (None, "idle"):
                workspace.brain_mode = "working"
        elif result.status == ExecutionStatus.AWAITING_CONFIRMATION:
            workspace.next_action = action
            workspace.running_tasks = []
            workspace.brain_mode = "awaiting_confirmation"
        elif result.status in (
            ExecutionStatus.BLOCKED,
            ExecutionStatus.FORBIDDEN,
        ):
            workspace.running_tasks = []
            if action:
                workspace.next_action = action
        elif result.status in (
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.WAITING,
        ):
            workspace.running_tasks = []
        elif result.status == ExecutionStatus.PENDING and action:
            workspace.next_action = action
            workspace.running_tasks = []

        # Phase 18.2 — concise safety mirror (no secrets).
        risk = task.risk_level or getattr(result, "risk_level", None)
        if hasattr(workspace, "current_execution_risk"):
            workspace.current_execution_risk = risk
        if hasattr(workspace, "confirmation_pending"):
            workspace.confirmation_pending = (
                result.status == ExecutionStatus.AWAITING_CONFIRMATION
            )
        if hasattr(workspace, "confirmation_id"):
            workspace.confirmation_id = (
                task.confirmation_id
                if result.status == ExecutionStatus.AWAITING_CONFIRMATION
                else None
            )
        if hasattr(workspace, "blocked_reason"):
            if result.status in (
                ExecutionStatus.BLOCKED,
                ExecutionStatus.FORBIDDEN,
            ):
                workspace.blocked_reason = task.blocked_reason or result.blocked_reason
            elif result.status == ExecutionStatus.AWAITING_CONFIRMATION:
                workspace.blocked_reason = None
            elif result.status in (
                ExecutionStatus.COMPLETED,
                ExecutionStatus.PARTIAL_SUCCESS,
                ExecutionStatus.RUNNING,
            ):
                workspace.blocked_reason = None

        # Phase 18.3 — tool bridge mirror (delegates to bridge when available).
        bridge = task.bridge_result
        if bridge is not None and hasattr(self._tool_bridge, "apply_workspace_update"):
            self._tool_bridge.apply_workspace_update(workspace, bridge)
        else:
            if hasattr(workspace, "last_tool"):
                workspace.last_tool = getattr(task, "last_tool", None)
            if hasattr(workspace, "last_execution"):
                workspace.last_execution = result.message
            if hasattr(workspace, "execution_duration"):
                workspace.execution_duration = round(float(result.duration), 4)
            if hasattr(workspace, "execution_status"):
                workspace.execution_status = result.status.value
            if hasattr(workspace, "last_error"):
                workspace.last_error = task.error if not result.success else None

        # Phase 18.4 — recovery mirror (lightweight fields only).
        self._recovery.apply_workspace_update(workspace)
        if hasattr(workspace, "execution_status") and result.status == ExecutionStatus.WAITING:
            workspace.execution_status = result.status.value

        logger.info(
            "EXECUTION_WORKSPACE_UPDATED action=%s status=%s next_action=%s "
            "running_tasks=%s risk=%s confirmation_pending=%s last_tool=%s "
            "retry_count=%s rollback_available=%s",
            action,
            result.status.value,
            getattr(workspace, "next_action", None),
            getattr(workspace, "running_tasks", None),
            getattr(workspace, "current_execution_risk", None),
            getattr(workspace, "confirmation_pending", None),
            getattr(workspace, "last_tool", None),
            getattr(workspace, "retry_count", None),
            getattr(workspace, "rollback_available", None),
        )

    def _maybe_feedback(
        self,
        decision_feedback: Callable[..., Any] | None,
        result: ExecutionResult,
        decision: Any | None,
        send_feedback: bool,
    ) -> None:
        """Return outcome feedback to DecisionEngine when requested."""
        if not send_feedback or decision_feedback is None:
            return
        if result.status == ExecutionStatus.AWAITING_CONFIRMATION:
            return
        if decision is None or not getattr(decision, "selected_action", None):
            if result.status == ExecutionStatus.CANCELLED:
                return
        try:
            decision_feedback(
                actual_result=result.actual_result,
                success=result.success,
                duration=result.duration,
                decision_id=result.decision_id
                or getattr(decision, "decision_id", None),
                selected_action=result.action
                or getattr(decision, "selected_action", None),
                expected_value=getattr(decision, "expected_value", None),
            )
        except TypeError:
            decision_feedback(
                actual_result=result.actual_result,
                success=result.success,
                duration=result.duration,
            )
        logger.info(
            "EXECUTION_FEEDBACK_SENT task_id=%s success=%s actual_result=%s",
            result.task_id,
            result.success,
            result.actual_result,
        )

    @staticmethod
    def _log_safety_evaluated(safety: ExecutionSafetyResult) -> None:
        logger.info(
            "EXECUTION_SAFETY_EVALUATED task_id=%s action=%s risk_level=%s "
            "decision=%s requires_confirmation=%s confirmation_id=%s",
            safety.task_id,
            safety.action,
            safety.risk_level.value,
            safety.decision.value,
            safety.requires_confirmation,
            safety.confirmation_id,
        )

    @staticmethod
    def _map_gate_risk(risk: ExecutionRiskLevel) -> RiskLevel:
        mapping = {
            ExecutionRiskLevel.SAFE_READ: RiskLevel.SAFE,
            ExecutionRiskLevel.LOW_RISK_WRITE: RiskLevel.MEDIUM,
            ExecutionRiskLevel.HIGH_RISK_WRITE: RiskLevel.HIGH,
            ExecutionRiskLevel.DESTRUCTIVE: RiskLevel.CRITICAL,
            ExecutionRiskLevel.FORBIDDEN: RiskLevel.CRITICAL,
        }
        return mapping.get(risk, RiskLevel.HIGH)

    def _expired_confirm_result(
        self,
        token: str,
        stamp: datetime,
        *,
        rejected: bool = False,
    ) -> ExecutionResult:
        message = (
            "Confirmation rejected"
            if rejected
            else "Confirmation expired or not found"
        )
        task = self._active_task
        if task is not None and task.status == ExecutionStatus.AWAITING_CONFIRMATION:
            task.status = ExecutionStatus.CANCELLED
            task.error = message
            task.completed_at = stamp
            task.updated_at = stamp
            result = ExecutionResult.from_task(
                task,
                message=message,
                success=False,
                actual_result=0.0,
                now=stamp,
            )
        else:
            result = ExecutionResult(
                task_id=getattr(task, "task_id", str(uuid.uuid4())),
                status=ExecutionStatus.CANCELLED,
                action=getattr(task, "action", None),
                success=False,
                message=message,
                duration=0.0,
                actual_result=0.0,
                completed_at=stamp,
                confirmation_id=token,
                error=message,
            )
        self._active_result = result
        return result

    def _duplicate_confirm_result(
        self,
        token: str,
        stamp: datetime,
    ) -> ExecutionResult:
        if self._active_result is not None:
            return self._active_result
        task = self._active_task
        return ExecutionResult(
            task_id=getattr(task, "task_id", str(uuid.uuid4())),
            status=getattr(task, "status", ExecutionStatus.COMPLETED),
            action=getattr(task, "action", None),
            success=getattr(task, "status", None) == ExecutionStatus.COMPLETED,
            message="Confirmation already processed — execution not repeated",
            duration=0.0,
            actual_result=1.0
            if getattr(task, "status", None) == ExecutionStatus.COMPLETED
            else 0.0,
            completed_at=stamp,
            confirmation_id=token,
        )

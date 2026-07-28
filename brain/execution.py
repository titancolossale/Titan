# =====================================
# Titan Execution System
# =====================================

"""Facade over ExecutionEngine (Phase 18.1–18.4).

Transforms DecisionEngine selections into ExecutionTask / ExecutionResult
while reusing PlanningEngine Plan and request-scoped WorkspaceState.
Phase 18.2 adds confirm / reject for safety-gated tasks.
Phase 18.3 routes approved execution through the Tool Execution Bridge.
Phase 18.4 adds rollback / resume recovery entry points.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping

from brain.execution_engine import ExecutionEngine
from brain.execution_models import ExecutionResult, ExecutionTask
from brain.execution_recovery import ExecutionRecoveryManager, RollbackRecord
from brain.execution_safety import PendingExecutionConfirmation
from brain.execution_tool_bridge import ToolExecutionBridge
from brain.planning_models import Plan


class Execution:
    """Cognitive execution facade — delegates to ExecutionEngine."""

    def __init__(self, engine: ExecutionEngine | None = None) -> None:
        self._engine = engine or ExecutionEngine()

    @property
    def engine(self) -> ExecutionEngine:
        return self._engine

    @property
    def tool_bridge(self) -> ToolExecutionBridge:
        return self._engine.tool_bridge

    @property
    def recovery_manager(self) -> ExecutionRecoveryManager:
        return self._engine.recovery_manager

    def execute_decision(
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
        """Create and run an ExecutionTask from the current Decision."""
        return self._engine.execute(
            decision=decision,
            plan=plan,
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=now,
            capability=capability,
            action_metadata=action_metadata,
            execution_mode=execution_mode,
            confirmation_token=confirmation_token,
            session_id=session_id,
            user=user,
            turn_id=turn_id,
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
        """Approve a pending execution confirmation (at most once)."""
        return self._engine.confirm(
            confirmation_id,
            workspace=workspace,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=now,
            session_id=session_id,
            user=user,
            turn_id=turn_id,
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
        """Reject a pending execution confirmation — never executes."""
        return self._engine.reject(
            confirmation_id,
            workspace=workspace,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=now,
            reason=reason,
        )

    def rollback(
        self,
        *,
        reason: str | None = None,
        rollback_fn: Callable[..., Any] | None = None,
        workspace: Any | None = None,
    ) -> RollbackRecord:
        """Rollback the last reversible execution when available."""
        return self._engine.rollback(
            reason=reason,
            rollback_fn=rollback_fn,
            workspace=workspace,
        )

    def resume_after_restart(
        self,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = False,
        now: datetime | None = None,
    ) -> ExecutionResult | None:
        """Resume or safely abort a persisted execution checkpoint."""
        return self._engine.resume_after_restart(
            workspace=workspace,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=now,
        )

    def resume_waiting(
        self,
        *,
        workspace: Any | None = None,
        decision_feedback: Callable[..., Any] | None = None,
        send_feedback: bool = True,
        now: datetime | None = None,
    ) -> ExecutionResult:
        """Continue a WAITING execution task."""
        return self._engine.resume_waiting(
            workspace=workspace,
            decision_feedback=decision_feedback,
            send_feedback=send_feedback,
            now=now,
        )

    def lookup_pending(
        self,
        confirmation_id: str,
    ) -> PendingExecutionConfirmation | None:
        return self._engine.lookup_pending(confirmation_id)

    @property
    def active_task(self) -> ExecutionTask | None:
        return self._engine.active_task

    @property
    def active_result(self) -> ExecutionResult | None:
        return self._engine.active_result

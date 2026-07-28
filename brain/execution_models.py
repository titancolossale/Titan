# =====================================
# Titan Execution Models
# =====================================

"""Execution types for next-action execution (Phase 18.1–18.4).

The Execution Engine takes a DecisionEngine selection and transforms it into
an ``ExecutionTask`` with shared ``ExecutionContext``. Reuses PlanningEngine
``Plan``, Decision, Goal / Project / Mission, and request-scoped WorkspaceState
— does not recreate those systems.

Phase 18.2 — safety evaluation and confirmation gate before side effects.
Phase 18.3 — Tool Execution Bridge outcomes.
Phase 18.4 — recovery / retry / rollback / resume metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    """Lifecycle of a cognitive next-action execution task.

    Phase 18.3 adds TIMEOUT and PARTIAL_SUCCESS for Tool Execution Bridge
    outcomes mirrored onto the cognitive ExecutionResult.
    Phase 18.4 adds WAITING for deferred resume / wait recovery.
    """

    PENDING = "PENDING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    FORBIDDEN = "FORBIDDEN"
    TIMEOUT = "TIMEOUT"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    WAITING = "WAITING"


@dataclass
class ExecutionContext:
    """Shared situational context for one execution task (Phase 18.1).

    Built once per execute() call and attached to the task — never duplicated
    across pipeline stages.
    """

    current_goal: str | None
    current_project: str | None
    current_mission: str | None
    current_plan: Any | None
    workspace_state: Any | None
    decision: Any | None

    def to_dict(self) -> dict[str, Any]:
        plan = self.current_plan
        decision = self.decision
        return {
            "current_goal": self.current_goal,
            "current_project": self.current_project,
            "current_mission": self.current_mission,
            "current_plan": (
                plan.to_dict()
                if plan is not None and hasattr(plan, "to_dict")
                else None
            ),
            "decision_id": getattr(decision, "decision_id", None),
            "selected_action": getattr(decision, "selected_action", None),
            "has_workspace": self.workspace_state is not None,
        }

    @classmethod
    def build(
        cls,
        *,
        decision: Any | None = None,
        plan: Any | None = None,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
    ) -> ExecutionContext:
        """Assemble context from hierarchy entities already resolved this turn."""
        goal_name = _entity_name(goal) or getattr(plan, "current_goal", None)
        if not goal_name and workspace is not None:
            goal_name = (
                getattr(workspace, "active_goal", None)
                or getattr(workspace, "current_goal", None)
            )
        project_name = _entity_name(project) or getattr(plan, "current_project", None)
        if not project_name and workspace is not None:
            project_name = getattr(workspace, "active_project", None)
        mission_name = _entity_name(mission, keys=("title", "name")) or getattr(
            plan, "current_mission", None
        )
        if not mission_name and workspace is not None:
            mission_name = (
                getattr(workspace, "active_mission_title", None)
                or getattr(workspace, "active_mission", None)
            )
        return cls(
            current_goal=goal_name,
            current_project=project_name,
            current_mission=mission_name,
            current_plan=plan,
            workspace_state=workspace,
            decision=decision,
        )


@dataclass
class ExecutionTask:
    """Executable unit derived from a Decision selection (Phase 18.1–18.2)."""

    action: str | None
    status: ExecutionStatus
    context: ExecutionContext
    created_at: datetime
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    blocked_reason: str | None = None
    error: str | None = None
    updated_at: datetime | None = None
    # Phase 18.2 — safety / confirmation (public fields only).
    safety: Any | None = None
    confirmation_id: str | None = None
    risk_level: str | None = None
    # Phase 18.3 — Tool Execution Bridge outcome (public summary only).
    bridge_result: Any | None = None
    last_tool: str | None = None
    # Phase 18.4 — recovery mirror (public fields only).
    recovery: Any | None = None
    attempt_number: int = 0
    recovery_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        safety = self.safety
        bridge = self.bridge_result
        recovery = self.recovery
        return {
            "task_id": self.task_id,
            "action": self.action,
            "status": self.status.value,
            "decision_id": self.decision_id,
            "created_at": self.created_at.isoformat(),
            "started_at": (
                self.started_at.isoformat() if self.started_at is not None else None
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at is not None else None
            ),
            "blocked_reason": self.blocked_reason,
            "error": self.error,
            "confirmation_id": self.confirmation_id,
            "risk_level": self.risk_level,
            "last_tool": self.last_tool,
            "attempt_number": self.attempt_number,
            "recovery_action": self.recovery_action,
            "bridge_result": (
                bridge.to_dict()
                if bridge is not None and hasattr(bridge, "to_dict")
                else None
            ),
            "safety": (
                safety.to_dict()
                if safety is not None and hasattr(safety, "to_dict")
                else None
            ),
            "recovery": (
                recovery.to_dict()
                if recovery is not None and hasattr(recovery, "to_dict")
                else None
            ),
            "context": self.context.to_dict(),
        }

    def format_for_prompt(self) -> str:
        """Current Execution block for PromptBuilder (Phase 18.1–18.4).

        Phase 18.3 exposes Last Tool / Execution Status / Execution Result
        only for bridge outcomes — never raw tool payloads.
        Phase 18.4 appends Execution Recovery / Retry Count /
        Rollback Available / Current Failure only.
        """
        bridge = self.bridge_result
        if bridge is not None and hasattr(bridge, "format_for_prompt"):
            parts = [str(bridge.format_for_prompt()).strip()]
        else:
            status_value = self.status.value
            result_text = self.error or self.blocked_reason or self.action or "None"
            parts = [
                f"Last Tool: {self.last_tool or 'None'}",
                f"Execution Status: {status_value}",
                f"Execution Result: {result_text}",
            ]
        safety = self.safety
        if safety is not None and hasattr(safety, "format_for_prompt"):
            safety_text = str(safety.format_for_prompt() or "").strip()
            if safety_text:
                parts.extend(["", safety_text])
        elif self.risk_level or self.blocked_reason or self.confirmation_id:
            parts.extend(["", "Execution Safety"])
            if self.risk_level:
                parts.append(f"Risk Level: {self.risk_level}")
            if self.status == ExecutionStatus.AWAITING_CONFIRMATION or self.confirmation_id:
                parts.append("Confirmation Required: yes")
            if self.blocked_reason and self.status in (
                ExecutionStatus.BLOCKED,
                ExecutionStatus.FORBIDDEN,
            ):
                parts.append(f"Blocked Reason: {self.blocked_reason}")
        recovery = self.recovery
        if recovery is not None and hasattr(recovery, "format_for_prompt"):
            recovery_text = str(recovery.format_for_prompt() or "").strip()
            if recovery_text:
                parts.extend(["", recovery_text])
        elif self.recovery_action or self.attempt_number or self.error:
            parts.extend(
                [
                    "",
                    "Execution Recovery",
                    f"Retry Count: {self.attempt_number}",
                    "Rollback Available: no",
                    f"Current Failure: {self.error or self.blocked_reason or 'None'}",
                ]
            )
        return "\n".join(parts)

    @classmethod
    def empty(
        cls,
        *,
        context: ExecutionContext,
        now: datetime | None = None,
        reason: str = "No selected action",
        status: ExecutionStatus = ExecutionStatus.CANCELLED,
    ) -> ExecutionTask:
        """Idle task when Decision has no selected_action."""
        stamp = now or datetime.now(timezone.utc)
        return cls(
            action=None,
            status=status,
            context=context,
            created_at=stamp,
            updated_at=stamp,
            completed_at=stamp,
            blocked_reason=reason if status == ExecutionStatus.BLOCKED else None,
            error=reason if status == ExecutionStatus.CANCELLED else None,
            decision_id=getattr(context.decision, "decision_id", None),
        )


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of one ExecutionTask lifecycle (Phase 18.1–18.4)."""

    task_id: str
    status: ExecutionStatus
    action: str | None
    success: bool
    message: str
    duration: float
    actual_result: float
    completed_at: datetime
    decision_id: str | None = None
    blocked_reason: str | None = None
    error: str | None = None
    confirmation_id: str | None = None
    risk_level: str | None = None
    requires_confirmation: bool = False
    # Phase 18.4 — recovery summary (public).
    recovery_action: str | None = None
    attempt_number: int = 0
    rollback_completed: bool = False
    execution_recovered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "action": self.action,
            "success": self.success,
            "message": self.message,
            "duration": self.duration,
            "actual_result": self.actual_result,
            "completed_at": self.completed_at.isoformat(),
            "decision_id": self.decision_id,
            "blocked_reason": self.blocked_reason,
            "error": self.error,
            "confirmation_id": self.confirmation_id,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "recovery_action": self.recovery_action,
            "attempt_number": self.attempt_number,
            "rollback_completed": self.rollback_completed,
            "execution_recovered": self.execution_recovered,
        }

    @classmethod
    def from_task(
        cls,
        task: ExecutionTask,
        *,
        message: str,
        success: bool,
        actual_result: float,
        duration: float = 0.0,
        now: datetime | None = None,
    ) -> ExecutionResult:
        stamp = now or task.completed_at or datetime.now(timezone.utc)
        safety = task.safety
        requires = bool(getattr(safety, "requires_confirmation", False))
        recovery = task.recovery
        rollback = getattr(recovery, "rollback", None) if recovery is not None else None
        return cls(
            task_id=task.task_id,
            status=task.status,
            action=task.action,
            success=success,
            message=message,
            duration=max(0.0, float(duration)),
            actual_result=max(0.0, min(1.0, float(actual_result))),
            completed_at=stamp,
            decision_id=task.decision_id,
            blocked_reason=task.blocked_reason,
            error=task.error,
            confirmation_id=task.confirmation_id,
            risk_level=task.risk_level,
            requires_confirmation=requires
            or task.status == ExecutionStatus.AWAITING_CONFIRMATION,
            recovery_action=task.recovery_action
            or (
                getattr(getattr(recovery, "last_recovery_action", None), "value", None)
                if recovery is not None
                else None
            ),
            attempt_number=int(
                task.attempt_number
                or getattr(recovery, "retry_count", 0)
                or 0
            ),
            rollback_completed=bool(
                getattr(rollback, "rollback_completed", False) if rollback else False
            ),
            execution_recovered=bool(
                getattr(recovery, "execution_recovered", False) if recovery else False
            ),
        )


@dataclass
class ExecutionHistory:
    """Rolling history of ExecutionResult entries (Phase 18.1)."""

    entries: list[ExecutionResult] = field(default_factory=list)
    limit: int = 50

    def append(self, result: ExecutionResult) -> None:
        """Append one result; trim oldest when over limit (single pass)."""
        self.entries.append(result)
        overflow = len(self.entries) - max(1, int(self.limit))
        if overflow > 0:
            del self.entries[:overflow]

    def recent(self, count: int = 5) -> list[ExecutionResult]:
        """Return the most recent results (oldest first among the slice)."""
        if count <= 0:
            return []
        return list(self.entries[-count:])

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _entity_name(entity: Any | None, keys: tuple[str, ...] = ("name", "title")) -> str | None:
    if entity is None:
        return None
    for key in keys:
        value = getattr(entity, key, None)
        if value:
            return str(value)
    if isinstance(entity, dict):
        for key in keys:
            value = entity.get(key)
            if value:
                return str(value)
    return None

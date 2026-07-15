# =====================================
# Titan Permission Facade
# =====================================

"""Unified permission evaluation — caller, action, and confirmation (Phase 12.8 — P128-003)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.decision.models import ToolDecisionReport
from tools.permission_engine import PermissionEngine, PermissionResult
from tools.permission_manager import (
    ActionPermissionResult,
    PermissionLevel,
    PermissionManager,
    resolve_tool_action,
)
from tools.tool_capability import ToolCapability
from tools.tool_policy import ToolPolicy
from tools.tool_run_models import ToolExecutionContext


@dataclass(frozen=True)
class UnifiedPermissionResult:
    """Combined outcome of caller and action-level permission checks."""

    allowed: bool
    level: PermissionLevel
    reason: str
    action: str
    confirmation_required: bool = False


@dataclass
class PermissionFacade:
    """Single entry point for permission evaluation before tool execution."""

    policy: ToolPolicy = field(default_factory=ToolPolicy)
    permission_engine: PermissionEngine | None = None
    permission_manager: PermissionManager | None = None

    def __post_init__(self) -> None:
        if self.permission_engine is None:
            self.permission_engine = PermissionEngine(policy=self.policy)
        if self.permission_manager is None:
            self.permission_manager = PermissionManager()

    @property
    def manager(self) -> PermissionManager:
        """Expose action-level manager for planner/orchestrator wiring."""
        assert self.permission_manager is not None
        return self.permission_manager

    def evaluate(
        self,
        tool_name: str,
        capability: ToolCapability | None,
        context: ToolExecutionContext,
        params: dict | None = None,
        *,
        decision_report: ToolDecisionReport | None = None,
    ) -> UnifiedPermissionResult:
        """Run caller and action permission checks once per invocation."""
        assert self.permission_engine is not None
        assert self.permission_manager is not None

        if capability is not None:
            engine_result = self.permission_engine.evaluate(
                tool_name,
                capability,
                context,
            )
            if not engine_result.allowed:
                action = resolve_tool_action(tool_name, params, decision_report)
                return UnifiedPermissionResult(
                    allowed=False,
                    level=PermissionLevel.BLOCKED,
                    reason=engine_result.reason,
                    action=action,
                )
        else:
            if not self.policy.is_allowed(context.caller, tool_name):
                action = resolve_tool_action(tool_name, params, decision_report)
                return UnifiedPermissionResult(
                    allowed=False,
                    level=PermissionLevel.BLOCKED,
                    reason=self.policy.deny_message(context.caller, tool_name),
                    action=action,
                )

        action_result = self.permission_manager.evaluate(
            tool_name,
            None,
            params,
            decision_report=decision_report,
            confirmed=context.confirmed,
        )

        if action_result.level == PermissionLevel.BLOCKED:
            return UnifiedPermissionResult(
                allowed=False,
                level=PermissionLevel.BLOCKED,
                reason=action_result.reason,
                action=action_result.action,
            )

        if action_result.level == PermissionLevel.CONFIRMATION_REQUIRED:
            if context.confirmed:
                return UnifiedPermissionResult(
                    allowed=True,
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason=action_result.reason,
                    action=action_result.action,
                    confirmation_required=False,
                )
            return UnifiedPermissionResult(
                allowed=False,
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=action_result.reason,
                action=action_result.action,
                confirmation_required=True,
            )

        return UnifiedPermissionResult(
            allowed=True,
            level=PermissionLevel.AUTO_ALLOWED,
            reason=action_result.reason,
            action=action_result.action,
        )

    def evaluate_action_only(
        self,
        tool_name: str,
        action: str | None,
        params: dict | None = None,
        *,
        decision_report: ToolDecisionReport | None = None,
        confirmed: bool = False,
    ) -> ActionPermissionResult:
        """Action-level check for orchestrator pre-flight (no capability required)."""
        assert self.permission_manager is not None
        return self.permission_manager.evaluate(
            tool_name,
            action,
            params,
            decision_report=decision_report,
            confirmed=confirmed,
        )

    def engine_result(
        self,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
    ) -> PermissionResult:
        """Expose engine-only check for legacy callers."""
        assert self.permission_engine is not None
        return self.permission_engine.evaluate(tool_name, capability, context)

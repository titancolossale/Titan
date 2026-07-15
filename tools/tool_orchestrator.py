# =====================================
# Titan Tool Orchestrator
# =====================================

"""Orchestrate interpreted tool requests with permission checks (Phase 12.6 Batch 1 — P126-003)."""

from __future__ import annotations

from dataclasses import dataclass

from core.execution_context import ExecutionDispatchContext
from tools.decision.execution_context import attach_decision_report
from tools.decision.models import ToolDecisionReport
from tools.natural_language_planner import NaturalLanguagePlanner
from tools.orchestration_models import (
    InterpretedToolRequest,
    OrchestrationStatus,
    ToolOrchestrationResult,
)
from tools.planner_models import PlannerResult, PlanStepKind
from tools.permission_facade import PermissionFacade
from tools.permission_manager import PermissionLevel, PermissionManager, resolve_tool_action
from tools.tool_executor import execute_tool
from tools.tool_manager import ToolManager
from tools.tool_policy import BRAIN_CALLER
from tools.tool_result import ToolRequest, ToolResult
from tools.tool_run_models import ToolRunStatus


@dataclass
class ToolOrchestrator:
    """Route interpreted tool requests through permission checks and ToolManager."""

    tool_manager: ToolManager
    permission_manager: PermissionManager | None = None
    permission_facade: PermissionFacade | None = None

    def __post_init__(self) -> None:
        if self.permission_facade is None:
            self.permission_facade = PermissionFacade(
                policy=self.tool_manager.policy,
            )
        if self.permission_manager is None:
            self.permission_manager = self.permission_facade.manager

    def orchestrate(
        self,
        request: InterpretedToolRequest,
        *,
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
        execute: bool = True,
    ) -> ToolOrchestrationResult:
        """Evaluate permission and optionally execute a single tool action."""
        assert self.permission_manager is not None

        report = decision_report
        selected_action = request.selected_action or resolve_tool_action(
            request.tool_name,
            request.params,
            report,
        )

        confirmed = False
        if dispatch_context is not None:
            confirmed = dispatch_context.confirmed
            if report is None:
                report = dispatch_context.decision_report

        assert self.permission_facade is not None
        permission = self.permission_facade.evaluate_action_only(
            request.tool_name,
            selected_action,
            request.params,
            decision_report=report,
            confirmed=confirmed,
        )

        if permission.level == PermissionLevel.BLOCKED:
            return ToolOrchestrationResult(
                orchestration_status=OrchestrationStatus.BLOCKED,
                selected_tool=request.tool_name,
                selected_action=selected_action,
                permission_level=permission.level,
                executed=False,
                confirmation_required=False,
                reason=permission.reason,
                result=ToolResult(
                    tool_name=request.tool_name,
                    success=False,
                    error=permission.reason,
                    source=request.tool_name,
                ),
            )

        if permission.level == PermissionLevel.CONFIRMATION_REQUIRED and not confirmed:
            return ToolOrchestrationResult(
                orchestration_status=OrchestrationStatus.PENDING_CONFIRMATION,
                selected_tool=request.tool_name,
                selected_action=selected_action,
                permission_level=permission.level,
                executed=False,
                confirmation_required=True,
                reason=permission.reason,
            )

        if not execute:
            return ToolOrchestrationResult(
                orchestration_status=OrchestrationStatus.SKIPPED,
                selected_tool=request.tool_name,
                selected_action=selected_action,
                permission_level=permission.level,
                executed=False,
                confirmation_required=False,
                reason="Exécution désactivée (évaluation uniquement).",
            )

        tool_result = self._execute_via_manager(
            request,
            dispatch_context=dispatch_context,
            decision_report=report,
        )
        status = (
            OrchestrationStatus.COMPLETED
            if tool_result.success
            else OrchestrationStatus.FAILED
        )
        if tool_result.metadata.get("status") == ToolRunStatus.PENDING_CONFIRMATION.value:
            status = OrchestrationStatus.PENDING_CONFIRMATION

        return ToolOrchestrationResult(
            orchestration_status=status,
            selected_tool=request.tool_name,
            selected_action=selected_action,
            permission_level=permission.level,
            executed=tool_result.success or status == OrchestrationStatus.PENDING_CONFIRMATION,
            confirmation_required=status == OrchestrationStatus.PENDING_CONFIRMATION,
            reason=permission.reason if tool_result.success else tool_result.error,
            result=tool_result,
        )

    def orchestrate_requests(
        self,
        requests: list[ToolRequest],
        *,
        message: str = "",
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
    ) -> list[ToolOrchestrationResult]:
        """Orchestrate a sequence of tool requests without starting unrelated tools."""
        results: list[ToolOrchestrationResult] = []
        for tool_request in requests:
            interpreted = InterpretedToolRequest(
                tool_name=tool_request.tool_name,
                params=dict(tool_request.params),
                message=message,
                caller=BRAIN_CALLER,
            )
            results.append(
                self.orchestrate(
                    interpreted,
                    dispatch_context=dispatch_context,
                    decision_report=decision_report,
                ),
            )
        return results

    def orchestrate_plan(
        self,
        planner_result: PlannerResult,
        *,
        message: str = "",
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
    ) -> list[ToolOrchestrationResult]:
        """Execute a structured plan in dependency order with fallback support."""
        step_by_id = {step.step_id: step for step in planner_result.steps}
        completed: set[str] = set()
        failed: set[str] = set()
        results: list[ToolOrchestrationResult] = []

        for step_id in planner_result.execution_order:
            step = step_by_id.get(step_id)
            if step is None:
                continue

            if not self._plan_step_ready(step, completed, failed):
                continue

            result = self.orchestrate(
                InterpretedToolRequest(
                    tool_name=step.required_tool,
                    params=dict(step.tool_params),
                    message=message,
                    selected_action=step.selected_action,
                    caller=BRAIN_CALLER,
                ),
                dispatch_context=dispatch_context,
                decision_report=decision_report,
            )
            results.append(result)

            if self._orchestration_succeeded(result):
                completed.add(step_id)
                continue

            failed.add(step_id)
            if step.fallback_tool and step.fallback_params is not None:
                fallback_result = self.orchestrate(
                    InterpretedToolRequest(
                        tool_name=step.fallback_tool,
                        params=dict(step.fallback_params),
                        message=message,
                        caller=BRAIN_CALLER,
                    ),
                    dispatch_context=dispatch_context,
                    decision_report=decision_report,
                )
                results.append(fallback_result)
                if self._orchestration_succeeded(fallback_result):
                    completed.add(step_id)

        return results

    @staticmethod
    def _orchestration_succeeded(result: ToolOrchestrationResult) -> bool:
        return result.orchestration_status in {
            OrchestrationStatus.COMPLETED,
            OrchestrationStatus.PENDING_CONFIRMATION,
        }

    @staticmethod
    def _plan_step_ready(
        step,
        completed: set[str],
        failed: set[str],
    ) -> bool:
        """Return True when a planned step should run given prior outcomes."""
        if step.step_kind == PlanStepKind.FALLBACK:
            if not step.dependencies:
                return False
            return step.dependencies[0] in failed

        if step.dependencies and not all(
            dependency in completed for dependency in step.dependencies
        ):
            return False

        if step.step_kind != PlanStepKind.CONDITIONAL:
            return True

        if step.condition == "primary_failed":
            return bool(step.dependencies) and step.dependencies[0] in failed

        if step.condition == "user_condition_met":
            return not step.dependencies or step.dependencies[0] not in failed

        if step.condition == "search_has_results":
            return bool(step.dependencies) and step.dependencies[0] in completed

        return True

    def orchestration_results_to_tool_results(
        self,
        results: list[ToolOrchestrationResult],
    ) -> list[ToolResult]:
        """Convert orchestration results to ToolResult list for Brain prompt assembly."""
        tool_results: list[ToolResult] = []
        for item in results:
            if item.result is not None:
                tool_results.append(item.result)
            elif item.orchestration_status == OrchestrationStatus.PENDING_CONFIRMATION:
                tool_results.append(
                    ToolResult(
                        tool_name=item.selected_tool or "unknown",
                        success=False,
                        error=item.reason,
                        source=item.selected_tool or "unknown",
                        metadata={
                            "orchestration_status": item.orchestration_status.value,
                            "confirmation_required": True,
                            "pending_confirmation": True,
                        },
                    ),
                )
            elif item.orchestration_status == OrchestrationStatus.BLOCKED:
                tool_results.append(
                    ToolResult(
                        tool_name=item.selected_tool or "unknown",
                        success=False,
                        error=item.reason,
                        source=item.selected_tool or "unknown",
                        metadata={
                            "orchestration_status": item.orchestration_status.value,
                            "permission_level": item.permission_level.value,
                        },
                    ),
                )
        return tool_results

    def _execute_via_manager(
        self,
        request: InterpretedToolRequest,
        *,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
    ) -> ToolResult:
        """Route execution through unified tool executor."""
        from core.execution_context import build_tool_execution_context

        dispatch = dispatch_context or ExecutionDispatchContext(
            user="Nolan",
            session_id="default",
            turn_id="default",
        )
        ctx = build_tool_execution_context(dispatch, caller=request.caller)
        if decision_report is not None:
            ctx = attach_decision_report(ctx, decision_report)

        result = execute_tool(
            self.tool_manager,
            request.tool_name,
            request.params,
            caller=request.caller,
            context=ctx,
        )
        metadata = dict(result.metadata)
        metadata["orchestration_status"] = (
            OrchestrationStatus.COMPLETED.value
            if result.success
            else OrchestrationStatus.FAILED.value
        )
        result.metadata = metadata
        return result

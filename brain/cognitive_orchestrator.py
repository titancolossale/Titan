# =====================================
# Titan Cognitive Orchestrator
# =====================================

"""Decision engine: plan before execute — Phase 24.0 (P24-001).

Architecture::

    User Request → Intent Analysis → Planner → Task Graph
        → Tool Selection → Execution → Verification → Response

ToolManager is the execution layer; this module is the intelligence layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from brain.cognitive_models import (
    CognitiveExecutionResult,
    CognitivePhase,
    CognitivePlan,
    PlanRuntimeState,
    PlanStatus,
    PlanVerificationResult,
    ProgressEvent,
    TaskGraph,
    TaskGraphNode,
    TaskNodeStatus,
    new_plan_id,
)
from brain.cognitive_progress import (
    progress_event,
    progress_label_for_phase,
    register_tool_presentation,
    resolve_neural_state,
    resolve_tool_phase,
    sync_registered_tools,
    task_node_from_plan_step,
)
from brain.decision_execution_bridge import (
    clarification_tool_result,
    fallback_confirmation_tool_result,
    no_capability_tool_result,
)
from brain.executor import Executor
from brain.reasoning import Reasoning
from core.execution_context import ExecutionDispatchContext
from core.execution_policy import ExecutionPolicy
from tools.decision.models import FallbackAction, ToolDecisionReport
from tools.natural_language_planner import NaturalLanguagePlanner, compute_execution_order
from tools.orchestration_models import OrchestrationStatus, ToolOrchestrationResult
from tools.planner_models import PlannerResult, PlanStepKind
from tools.providers.provider_fallback_policy import FallbackDecision
from tools.reasoning_loop import ReasoningLoop, ReviewedPlannerResult
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest, ToolResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class CognitiveOrchestrator:
    """Titan's cognitive decision engine — plans before executing tools."""

    reasoning: Reasoning
    planner: NaturalLanguagePlanner
    reasoning_loop: ReasoningLoop
    tool_orchestrator: ToolOrchestrator
    executor: Executor
    policy: ExecutionPolicy
    tool_manager: ToolManager | None = None
    on_progress: ProgressCallback | None = None
    _active: dict[str, PlanRuntimeState] = field(default_factory=dict)
    _suspended: dict[str, tuple[CognitivePlan, PlanRuntimeState]] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        if self.tool_manager is None:
            self.tool_manager = self.tool_orchestrator.tool_manager
        self._sync_tool_registry()

    # ------------------------------------------------------------------
    # Public planner API (camelCase aliases for external bridges)
    # ------------------------------------------------------------------

    def create_plan(
        self,
        message: str,
        *,
        analysis: dict[str, Any] | None = None,
        availability_resolver=None,
        decision_report: ToolDecisionReport | None = None,
    ) -> CognitivePlan:
        """Intent analysis → structured plan → task graph."""
        plan_id = new_plan_id()
        runtime = PlanRuntimeState(plan_id=plan_id, status=PlanStatus.CREATED)
        self._active[plan_id] = runtime
        self._emit(progress_event(CognitivePhase.UNDERSTANDING), plan_id=plan_id)

        if analysis is None:
            analysis = self.reasoning.analyze(
                message,
                availability_resolver=availability_resolver,
            )

        report = decision_report or analysis.get("decision_report")
        if not isinstance(report, ToolDecisionReport):
            report = None

        self._emit(progress_event(CognitivePhase.PLANNING), plan_id=plan_id)

        planner_result = self.planner.plan(message, analysis, decision_report=report)
        reviewed = self.reasoning_loop.review(
            planner_result,
            message=message,
            decision_report=report,
            analysis=analysis,
        )
        planner_result = reviewed.planner_result
        analysis["planner_result"] = planner_result
        analysis["reviewed_planner_result"] = reviewed

        task_graph = self._build_task_graph(planner_result, registered_tools=self._registered_tools())

        cognitive_plan = CognitivePlan(
            plan_id=plan_id,
            message=message,
            task_graph=task_graph,
            planner_result=planner_result,
            execution_plan=planner_result.plan,
            analysis=analysis,
            requires_confirmation=planner_result.requires_confirmation,
            clarification_required=reviewed.clarification_required,
            clarification_message=reviewed.clarification_message,
        )

        for node in task_graph.nodes:
            if self._should_skip_node(node, registered=self._registered_tools()):
                runtime.node_status[node.node_id] = TaskNodeStatus.SKIPPED
                runtime.skipped_nodes.add(node.node_id)
            else:
                runtime.node_status[node.node_id] = TaskNodeStatus.PENDING

        logger.debug(
            "Cognitive plan created: id=%s steps=%d tools=%s",
            plan_id,
            cognitive_plan.total_steps,
            cognitive_plan.estimated_tools,
        )
        return cognitive_plan

    createPlan = create_plan

    def execute_plan(
        self,
        plan: CognitivePlan,
        *,
        message: str = "",
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
        tool_requests_override: list[ToolRequest] | None = None,
    ) -> PlanRuntimeState:
        """Execute task graph via ToolOrchestrator — never call ToolManager directly."""
        runtime = self._active.get(plan.plan_id)
        if runtime is None:
            runtime = PlanRuntimeState(plan_id=plan.plan_id)
            self._active[plan.plan_id] = runtime

        if runtime.status == PlanStatus.CANCELLED:
            return runtime

        runtime.status = PlanStatus.EXECUTING
        report = decision_report or plan.analysis.get("decision_report")
        if not isinstance(report, ToolDecisionReport):
            report = None

        if plan.clarification_required:
            runtime.status = PlanStatus.SUSPENDED
            self._suspended[plan.plan_id] = (plan, runtime)
            return runtime

        guarded = self._decision_guard_results(report)
        if guarded is not None:
            runtime.tool_results = guarded
            runtime.status = PlanStatus.COMPLETED
            return runtime

        if tool_requests_override is not None:
            orchestration_results = self._execute_override_requests(
                tool_requests_override,
                message=message or plan.message,
                dispatch_context=dispatch_context,
                decision_report=report,
                runtime=runtime,
                plan=plan,
            )
        elif plan.total_steps == 0:
            orchestration_results = self._execute_direct_analysis(
                plan,
                message=message or plan.message,
                dispatch_context=dispatch_context,
                decision_report=report,
                runtime=runtime,
            )
        else:
            orchestration_results = self._execute_task_graph(
                plan,
                runtime=runtime,
                message=message or plan.message,
                dispatch_context=dispatch_context,
                decision_report=report,
            )

        runtime.orchestration_results = orchestration_results
        runtime.tool_results = self.tool_orchestrator.orchestration_results_to_tool_results(
            orchestration_results,
        )
        runtime.status = PlanStatus.EXECUTING
        return runtime

    executePlan = execute_plan

    def verify_plan(
        self,
        plan: CognitivePlan,
        runtime: PlanRuntimeState,
    ) -> PlanVerificationResult:
        """Verify execution outcomes before response synthesis."""
        self._emit(progress_event(CognitivePhase.VERIFICATION))
        runtime.status = PlanStatus.VERIFYING

        pending_confirmation = any(
            item.orchestration_status == OrchestrationStatus.PENDING_CONFIRMATION
            for item in runtime.orchestration_results
        )
        if pending_confirmation:
            runtime.verification_passed = True
            runtime.verification_summary = "Confirmation requise avant exécution."
            runtime.status = PlanStatus.SUSPENDED
            result = PlanVerificationResult(
                passed=True,
                summary=runtime.verification_summary,
                pending_confirmation=True,
            )
            self._emit(progress_event(CognitivePhase.VERIFICATION))
            return result

        if plan.clarification_required:
            runtime.verification_passed = False
            runtime.verification_summary = plan.clarification_message or "Clarification requise."
            runtime.status = PlanStatus.SUSPENDED
            return PlanVerificationResult(
                passed=False,
                summary=runtime.verification_summary,
            )

        required_nodes = [
            node
            for node in plan.task_graph.nodes
            if node.step_kind not in {PlanStepKind.CONDITIONAL, PlanStepKind.FALLBACK}
            and runtime.node_status.get(node.node_id) != TaskNodeStatus.SKIPPED
        ]

        failed_ids: list[str] = []
        for node in required_nodes:
            status = runtime.node_status.get(node.node_id, TaskNodeStatus.PENDING)
            if status == TaskNodeStatus.FAILED:
                failed_ids.append(node.node_id)

        if plan.total_steps == 0 and not runtime.tool_results:
            runtime.verification_passed = True
            runtime.verification_summary = "Aucun outil requis."
            runtime.status = PlanStatus.COMPLETED
            return PlanVerificationResult(passed=True, summary=runtime.verification_summary)

        passed = not failed_ids
        if passed:
            runtime.verification_passed = True
            runtime.verification_summary = "Exécution vérifiée."
            runtime.status = PlanStatus.COMPLETED
        else:
            runtime.verification_passed = False
            runtime.verification_summary = f"{len(failed_ids)} étape(s) en échec."
            runtime.status = PlanStatus.FAILED

        self._emit(progress_event(CognitivePhase.IDLE))
        return PlanVerificationResult(
            passed=passed,
            summary=runtime.verification_summary,
            failed_node_ids=tuple(failed_ids),
        )

    verifyPlan = verify_plan

    def retry_step(
        self,
        plan: CognitivePlan,
        step_id: str,
        *,
        message: str = "",
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
    ) -> PlanRuntimeState:
        """Retry a failed plan step through ToolOrchestrator."""
        runtime = self._active.get(plan.plan_id)
        if runtime is None:
            raise KeyError(f"Plan runtime not found: {plan.plan_id}")

        step = plan.planner_result.get_step(step_id)
        if step is None:
            raise KeyError(f"Step not found: {step_id}")

        node = plan.task_graph.get_node(step_id)
        runtime.current_node_id = step_id
        runtime.node_status[step_id] = TaskNodeStatus.RUNNING
        if node is not None:
            self._emit(progress_event(node.cognitive_phase, tool_name=node.tool, node_id=step_id))

        report = decision_report or plan.analysis.get("decision_report")
        from tools.orchestration_models import InterpretedToolRequest
        from tools.tool_policy import BRAIN_CALLER

        result = self.tool_orchestrator.orchestrate(
            InterpretedToolRequest(
                tool_name=step.required_tool,
                params=dict(step.tool_params),
                message=message or plan.message,
                selected_action=step.selected_action,
                caller=BRAIN_CALLER,
            ),
            dispatch_context=dispatch_context,
            decision_report=report if isinstance(report, ToolDecisionReport) else None,
        )
        runtime.orchestration_results.append(result)
        tool_results = self.tool_orchestrator.orchestration_results_to_tool_results([result])
        runtime.tool_results.extend(tool_results)

        if self._orchestration_succeeded(result):
            runtime.node_status[step_id] = TaskNodeStatus.COMPLETED
            runtime.completed_nodes.add(step_id)
            runtime.failed_nodes.discard(step_id)
        else:
            runtime.node_status[step_id] = TaskNodeStatus.FAILED
            runtime.failed_nodes.add(step_id)

        runtime.current_node_id = None
        return runtime

    retryStep = retry_step

    def cancel_plan(self, plan_id: str) -> PlanRuntimeState | None:
        """Cancel an active or suspended plan."""
        runtime = self._active.get(plan_id)
        if runtime is None:
            suspended = self._suspended.pop(plan_id, None)
            if suspended is None:
                return None
            _, runtime = suspended

        runtime.status = PlanStatus.CANCELLED
        runtime.current_node_id = None
        for node_id, status in list(runtime.node_status.items()):
            if status in {TaskNodeStatus.PENDING, TaskNodeStatus.RUNNING}:
                runtime.node_status[node_id] = TaskNodeStatus.CANCELLED

        self._emit(progress_event(CognitivePhase.IDLE))
        self._active.pop(plan_id, None)
        self._suspended.pop(plan_id, None)
        return runtime

    cancelPlan = cancel_plan

    def resume_plan(
        self,
        plan_id: str,
        *,
        message: str = "",
        dispatch_context: ExecutionDispatchContext | None = None,
        decision_report: ToolDecisionReport | None = None,
    ) -> CognitiveExecutionResult | None:
        """Resume a suspended plan from the next pending step."""
        entry = self._suspended.pop(plan_id, None)
        if entry is None:
            runtime = self._active.get(plan_id)
            if runtime is None or runtime.status != PlanStatus.SUSPENDED:
                return None
            plan = self._plan_for_runtime(plan_id)
            if plan is None:
                return None
        else:
            plan, runtime = entry

        self._active[plan_id] = runtime
        runtime.status = PlanStatus.EXECUTING

        pending_ids = [
            node_id
            for node_id in plan.task_graph.execution_order
            if runtime.node_status.get(node_id) == TaskNodeStatus.PENDING
        ]
        for node_id in pending_ids:
            step = plan.planner_result.get_step(node_id)
            if step is None:
                continue
            self.retry_step(
                plan,
                node_id,
                message=message,
                dispatch_context=dispatch_context,
                decision_report=decision_report,
            )

        verification = self.verify_plan(plan, runtime)
        return CognitiveExecutionResult(
            plan=plan,
            runtime=runtime,
            verification=verification,
            tool_results=tuple(runtime.tool_results),
            orchestration_results=tuple(runtime.orchestration_results),
        )

    resumePlan = resume_plan

    def get_runtime(self, plan_id: str) -> PlanRuntimeState | None:
        """Return runtime state for an active or suspended plan."""
        runtime = self._active.get(plan_id)
        if runtime is not None:
            return runtime
        entry = self._suspended.get(plan_id)
        if entry is not None:
            return entry[1]
        return None

    def run_turn(
        self,
        message: str,
        *,
        availability_resolver=None,
        dispatch_context: ExecutionDispatchContext | None = None,
        tool_requests_override: list[ToolRequest] | None = None,
        analysis: dict[str, Any] | None = None,
    ) -> CognitiveExecutionResult:
        """Full cognitive pipeline: create → execute → verify."""
        plan = self.create_plan(
            message,
            analysis=analysis,
            availability_resolver=availability_resolver,
        )
        report = plan.analysis.get("decision_report")
        decision_report = report if isinstance(report, ToolDecisionReport) else None

        runtime = self.execute_plan(
            plan,
            message=message,
            dispatch_context=dispatch_context,
            decision_report=decision_report,
            tool_requests_override=tool_requests_override,
        )
        verification = self.verify_plan(plan, runtime)
        return CognitiveExecutionResult(
            plan=plan,
            runtime=runtime,
            verification=verification,
            tool_results=tuple(runtime.tool_results),
            orchestration_results=tuple(runtime.orchestration_results),
        )

    def current_neural_state(self, plan_id: str | None = None) -> str:
        """Resolve brain_cognitive.js state for the active plan."""
        if plan_id is None and self._active:
            plan_id = next(iter(self._active))
        if plan_id is None:
            return resolve_neural_state(CognitivePhase.IDLE)

        runtime = self._active.get(plan_id)
        if runtime is None or runtime.current_node_id is None:
            if runtime and runtime.status == PlanStatus.VERIFYING:
                return resolve_neural_state(CognitivePhase.VERIFICATION)
            return resolve_neural_state(CognitivePhase.IDLE)

        return resolve_neural_state(
            CognitivePhase.PLANNING,
            tool_name=None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decision_guard_results(
        decision_report: ToolDecisionReport | None,
    ) -> list[ToolResult] | None:
        """Return early tool results when decision engine blocks execution."""
        if decision_report is None:
            return None
        if decision_report.fallback_action == FallbackAction.NO_CAPABILITY:
            return [no_capability_tool_result(decision_report)]
        if decision_report.fallback_action == FallbackAction.CLARIFICATION:
            return [clarification_tool_result(decision_report)]
        if (
            decision_report.fallback_decision
            == FallbackDecision.REQUEST_CONFIRMATION.value
        ):
            return [fallback_confirmation_tool_result(decision_report)]
        return None

    def _sync_tool_registry(self) -> None:
        if self.tool_manager is None:
            return
        for name in self.tool_manager.list_tools():
            register_tool_presentation(name)
        sync_registered_tools(self.tool_manager.list_tools())

    def _registered_tools(self) -> frozenset[str]:
        if self.tool_manager is None:
            return frozenset()
        return frozenset(self.tool_manager.list_tools())

    def _build_task_graph(
        self,
        planner_result: PlannerResult,
        *,
        registered_tools: frozenset[str],
    ) -> TaskGraph:
        nodes: list[TaskGraphNode] = []
        for step in planner_result.steps:
            if step.step_kind == PlanStepKind.CONDITIONAL:
                continue
            node = task_node_from_plan_step(step)
            if node.tool and node.tool not in registered_tools:
                continue
            nodes.append(node)

        order = compute_execution_order(tuple(
            step for step in planner_result.steps
            if step.step_id in {n.node_id for n in nodes}
        ))
        if not order:
            order = planner_result.execution_order

        return TaskGraph(nodes=tuple(nodes), execution_order=order)

    @staticmethod
    def _should_skip_node(node: TaskGraphNode, *, registered: frozenset[str]) -> bool:
        if node.tool is None:
            return True
        if node.tool not in registered:
            return True
        if node.step_kind == PlanStepKind.CONDITIONAL:
            return True
        return False

    def _execute_task_graph(
        self,
        plan: CognitivePlan,
        *,
        runtime: PlanRuntimeState,
        message: str,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
    ) -> list[ToolOrchestrationResult]:
        from tools.orchestration_models import InterpretedToolRequest
        from tools.tool_policy import BRAIN_CALLER

        results: list[ToolOrchestrationResult] = []
        step_by_id = {step.step_id: step for step in plan.planner_result.steps}
        completed: set[str] = set(runtime.completed_nodes)
        failed: set[str] = set(runtime.failed_nodes)

        for node_id in plan.task_graph.execution_order:
            if runtime.status == PlanStatus.CANCELLED:
                break

            status = runtime.node_status.get(node_id, TaskNodeStatus.PENDING)
            if status in {
                TaskNodeStatus.SKIPPED,
                TaskNodeStatus.COMPLETED,
                TaskNodeStatus.CANCELLED,
            }:
                continue

            step = step_by_id.get(node_id)
            node = plan.task_graph.get_node(node_id)
            if step is None or node is None:
                continue

            if not self.tool_orchestrator._plan_step_ready(step, completed, failed):
                continue

            runtime.current_node_id = node_id
            runtime.node_status[node_id] = TaskNodeStatus.RUNNING
            self._emit(
                progress_event(node.cognitive_phase, tool_name=node.tool, node_id=node_id),
                plan_id=plan.plan_id,
            )

            result = self.tool_orchestrator.orchestrate(
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
                runtime.node_status[node_id] = TaskNodeStatus.COMPLETED
                runtime.completed_nodes.add(node_id)
                completed.add(node_id)
                continue

            runtime.node_status[node_id] = TaskNodeStatus.FAILED
            runtime.failed_nodes.add(node_id)
            failed.add(node_id)

            if step.fallback_tool and step.fallback_params is not None:
                fallback_result = self.tool_orchestrator.orchestrate(
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
                    runtime.node_status[node_id] = TaskNodeStatus.COMPLETED
                    runtime.completed_nodes.add(node_id)
                    completed.add(node_id)
                    failed.discard(node_id)

        runtime.current_node_id = None
        return results

    def _execute_direct_analysis(
        self,
        plan: CognitivePlan,
        *,
        message: str,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
        runtime: PlanRuntimeState,
    ) -> list[ToolOrchestrationResult]:
        """Fallback when planner produced no steps but analysis has tool requests."""
        requests = plan.analysis.get("tool_requests") or []
        if not isinstance(requests, list) or not requests:
            if plan.analysis.get("needs_tool"):
                requests = self.executor.plan_tools(plan.analysis)
            else:
                return []

        allowed = self.policy.clamp_tool_count(len(requests))
        requests = requests[:allowed]

        for request in requests:
            self._emit(progress_event(
                resolve_tool_phase(request.tool_name),
                tool_name=request.tool_name,
            ))

        return self.tool_orchestrator.orchestrate_requests(
            requests,
            message=message,
            dispatch_context=dispatch_context,
            decision_report=decision_report,
        )

    def _execute_override_requests(
        self,
        requests: list[ToolRequest],
        *,
        message: str,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
        runtime: PlanRuntimeState,
        plan: CognitivePlan,
    ) -> list[ToolOrchestrationResult]:
        allowed = self.policy.clamp_tool_count(len(requests))
        requests = requests[:allowed]
        for request in requests:
            self._emit(progress_event(
                resolve_tool_phase(request.tool_name),
                tool_name=request.tool_name,
            ))
        return self.tool_orchestrator.orchestrate_requests(
            requests,
            message=message,
            dispatch_context=dispatch_context,
            decision_report=decision_report,
        )

    @staticmethod
    def _orchestration_succeeded(result: ToolOrchestrationResult) -> bool:
        return result.orchestration_status in {
            OrchestrationStatus.COMPLETED,
            OrchestrationStatus.PENDING_CONFIRMATION,
        }

    def _emit(self, event: ProgressEvent, *, plan_id: str | None = None) -> None:
        if plan_id is not None:
            runtime = self._active.get(plan_id)
            if runtime is not None:
                runtime.record_progress(event)
        elif self._active:
            latest_id = next(reversed(self._active))
            self._active[latest_id].record_progress(event)
        if self.on_progress is not None:
            self.on_progress(event)

    def _plan_for_runtime(self, plan_id: str) -> CognitivePlan | None:
        entry = self._suspended.get(plan_id)
        if entry is not None:
            return entry[0]
        return None

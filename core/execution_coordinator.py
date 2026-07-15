# =====================================
# Titan Execution Coordinator
# =====================================

"""Unified agent + tool dispatch with policy enforcement (Phase 8 — P8-062)."""

from __future__ import annotations

import logging

from agents.agent_context import AgentContext
from brain.cognitive_models import CognitiveExecutionResult
from brain.cognitive_orchestrator import CognitiveOrchestrator
from brain.cognitive_stream import CognitiveStreamEmitter, intent_label
from brain.decision_execution_bridge import (
    availability_resolver_from_manager,
    clarification_tool_result,
    fallback_confirmation_tool_result,
    no_capability_tool_result,
)
from brain.executor import Executor
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_context import ExecutionDispatchContext
from core.execution_policy import ExecutionPolicy
from core.execution_result import ExecutionResult
from core.task_orchestrator import TaskOrchestrator
from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.models import (
    FallbackAction,
    ToolDecisionReport,
    enrich_task_execution_decision_context,
)
from tools.decision.search_chain import (
    ambiguity_tool_result,
    build_search_query,
    extract_search_results,
    no_match_tool_result,
    read_tool_request,
    select_strong_matches,
)
from tools.decision.modification_guidance import (
    format_modification_plan_summary,
    format_patch_application_summary,
)
from tools.decision.task_execution_engine import TaskExecutionEngine
from tools.decision.task_execution_guidance import format_task_execution_results
from tools.decision.task_execution_models import (
    TaskExecutionPlan,
    TaskExecutionReport,
    TaskExecutionStep,
)
from tools.decision.workspace_guidance import (
    collect_files_read,
    format_workspace_tool_results,
)
from tools.decision.workspace_param_parser import parse_workspace_params
from tools.providers.provider_fallback_policy import FallbackDecision
from tools.natural_language_planner import NaturalLanguagePlanner
from tools.reasoning_loop import ReasoningLoop, ReviewedPlannerResult, reasoning_clarification_tool_result
from tools.tool_enums import RiskLevel
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest, ToolResult

logger = logging.getLogger(__name__)


class ExecutionCoordinator:
    """Merge TaskOrchestrator, Executor, and ToolDispatcher under one policy."""

    def __init__(
        self,
        task_orchestrator: TaskOrchestrator,
        tool_dispatcher: ToolDispatcher,
        *,
        reasoning: Reasoning | None = None,
        executor: Executor | None = None,
        policy: ExecutionPolicy | None = None,
        tool_orchestrator: ToolOrchestrator | None = None,
        planner: NaturalLanguagePlanner | None = None,
        reasoning_loop: ReasoningLoop | None = None,
        cognitive_orchestrator: CognitiveOrchestrator | None = None,
    ) -> None:
        self.task_orchestrator = task_orchestrator
        self.tool_dispatcher = tool_dispatcher
        self.reasoning = reasoning or Reasoning()
        self.executor = executor or Executor()
        self.policy = policy or ExecutionPolicy()
        self.tool_orchestrator = tool_orchestrator or ToolOrchestrator(
            tool_dispatcher.tool_manager,
        )
        self.planner = planner or NaturalLanguagePlanner(
            permission_manager=self.tool_orchestrator.permission_manager,
        )
        self.reasoning_loop = reasoning_loop or ReasoningLoop(
            permission_manager=self.tool_orchestrator.permission_manager,
        )
        self.cognitive_orchestrator = cognitive_orchestrator or CognitiveOrchestrator(
            reasoning=self.reasoning,
            planner=self.planner,
            reasoning_loop=self.reasoning_loop,
            tool_orchestrator=self.tool_orchestrator,
            executor=self.executor,
            policy=self.policy,
            tool_manager=tool_dispatcher.tool_manager,
        )

    def execute(
        self,
        message: str,
        *,
        agent_context: AgentContext | None = None,
        dispatch_context: ExecutionDispatchContext | None = None,
        tool_requests_override: list[ToolRequest] | None = None,
        stream: CognitiveStreamEmitter | None = None,
    ) -> ExecutionResult:
        """Run agents and tools sequentially according to policy."""
        availability = availability_resolver_from_manager(
            self.tool_dispatcher.tool_manager,
        )
        analysis = self.reasoning.analyze(
            message,
            availability_resolver=availability,
        )
        decision_report = analysis.get("decision_report")
        if not isinstance(decision_report, ToolDecisionReport):
            decision_report = None

        if stream is not None:
            intent_key = "general_chat"
            selected_tool = None
            if decision_report is not None:
                intent_key = getattr(
                    decision_report.intent,
                    "value",
                    str(decision_report.intent),
                )
                selected_tool = decision_report.selected_tool
            stream.emit(
                "intent_detected",
                {
                    "label": f"Intention : {intent_label(intent_key)}",
                    "intent": intent_key,
                    "selected_tool": selected_tool,
                    "neural_state": "thinking",
                },
            )

        if tool_requests_override is not None:
            tool_requests = self._plan_tools_override(tool_requests_override)
        else:
            tool_requests = None

        cognitive_plan = self.cognitive_orchestrator.create_plan(
            message,
            analysis=analysis,
            decision_report=decision_report,
        )
        planner_result = cognitive_plan.planner_result
        reviewed_result = cognitive_plan.analysis.get("reviewed_planner_result")
        if not isinstance(reviewed_result, ReviewedPlannerResult):
            reviewed_result = None
        if tool_requests is None and reviewed_result is not None:
            tool_requests = self._plan_tools(analysis, planner_result)
        analysis["planner_result"] = planner_result
        if reviewed_result is not None:
            analysis["reviewed_planner_result"] = reviewed_result
        if (
            reviewed_result is not None
            and reviewed_result.clarification_required
            and not self._decision_engine_overrides_clarification(
                decision_report,
                analysis,
            )
        ):
            action_label = self.executor.execute(analysis)
            agent_results = self._run_agents(message, agent_context)
            clarification = reasoning_clarification_tool_result(reviewed_result)
            runtime = self.cognitive_orchestrator.get_runtime(cognitive_plan.plan_id)
            if runtime is None:
                raise RuntimeError(f"Missing runtime for plan {cognitive_plan.plan_id}")
            cognitive_execution = CognitiveExecutionResult(
                plan=cognitive_plan,
                runtime=runtime,
                verification=self.cognitive_orchestrator.verify_plan(
                    cognitive_plan,
                    runtime,
                ),
                tool_results=(clarification,),
                orchestration_results=(),
            )
            return ExecutionResult(
                agent_results=agent_results,
                agent_results_text=self.task_orchestrator.format_results(agent_results),
                tool_results=[clarification],
                tool_results_text=clarification.error or "",
                action_label=action_label,
                decision_report=decision_report,
                cognitive_execution=cognitive_execution,
            )
        action_label = self.executor.execute(analysis)

        agent_results = self._run_agents(message, agent_context)
        task_plan = analysis.get("task_execution_plan")
        task_execution_report = None
        cognitive_execution: CognitiveExecutionResult | None = None
        if isinstance(task_plan, TaskExecutionPlan):
            tool_results, task_execution_report = self._run_multi_step_task(
                task_plan,
                dispatch_context,
                decision_report,
            )
        else:
            override = tool_requests if tool_requests_override is not None else None
            runtime = self.cognitive_orchestrator.execute_plan(
                cognitive_plan,
                message=message,
                dispatch_context=dispatch_context,
                decision_report=decision_report,
                tool_requests_override=override,
            )
            verification = self.cognitive_orchestrator.verify_plan(
                cognitive_plan,
                runtime,
            )
            tool_results = list(runtime.tool_results)
            cognitive_execution = CognitiveExecutionResult(
                plan=cognitive_plan,
                runtime=runtime,
                verification=verification,
                tool_results=tuple(tool_results),
                orchestration_results=tuple(runtime.orchestration_results),
            )
        tool_results, decision_report = self._apply_search_chain(
            message,
            analysis,
            tool_results,
            decision_report,
            dispatch_context,
        )
        decision_report = self._enrich_decision_report(decision_report, tool_results)
        if task_execution_report is not None:
            analysis["task_execution_report"] = task_execution_report
            if decision_report is not None:
                decision_report = enrich_task_execution_decision_context(
                    decision_report,
                    task_execution_report,
                )
            else:
                from tools.decision.intent import Intent

                decision_report = enrich_task_execution_decision_context(
                    ToolDecisionReport(
                        intent=Intent.WORKSPACE_EXPLAIN,
                        confidence=0.8,
                        tool_required=True,
                        candidate_tools=(),
                        selected_tool=None,
                        decision_reason="Exécution multi-étapes",
                        risk_level=RiskLevel.LOW,
                        confirmation_required=False,
                    ),
                    task_execution_report,
                )
        tool_results_text = self.tool_dispatcher.format_results(tool_results)
        tool_results_text = self._format_workspace_results(
            tool_results_text,
            decision_report,
            analysis,
        )
        tool_results_text = self._format_modification_results(
            tool_results_text,
            decision_report,
            analysis,
        )
        tool_results_text = self._format_patch_application_results(
            tool_results_text,
            decision_report,
            analysis,
        )
        tool_results_text = self._format_rollback_results(
            tool_results_text,
            decision_report,
            analysis,
        )
        tool_results_text = self._format_task_execution_results(
            tool_results_text,
            decision_report,
            analysis,
        )

        return ExecutionResult(
            agent_results=agent_results,
            agent_results_text=self.task_orchestrator.format_results(agent_results),
            tool_results=tool_results,
            tool_results_text=tool_results_text,
            action_label=action_label,
            decision_report=decision_report,
            cognitive_execution=cognitive_execution,
        )

    @staticmethod
    def _decision_engine_overrides_clarification(
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> bool:
        """Return True when decision engine or workspace routing should run despite planner clarification."""
        if decision_report is None:
            return False
        if decision_report.fallback_action in {
            FallbackAction.NO_CAPABILITY,
            FallbackAction.CLARIFICATION,
        }:
            return True
        if decision_report.fallback_decision == FallbackDecision.REQUEST_CONFIRMATION.value:
            return True
        if decision_report.confirmation_required:
            return True
        if decision_report.workspace_operation:
            return True
        if isinstance(analysis.get("task_execution_plan"), TaskExecutionPlan):
            return True
        return False

    @staticmethod
    def _enrich_decision_report(
        decision_report: ToolDecisionReport | None,
        tool_results: list,
    ) -> ToolDecisionReport | None:
        """Attach provider execution metadata from tool results (P10B-205)."""
        if decision_report is None:
            return decision_report
        enriched = decision_report
        if tool_results:
            for tool_result in tool_results:
                metadata = getattr(tool_result, "metadata", None) or {}
                updated = enrich_decision_report_from_result(enriched, metadata)
                if updated is not None and updated.selected_provider:
                    enriched = updated
            files_read = collect_files_read(tool_results)
            if files_read:
                enriched = enriched.with_workspace_context(
                    workspace_operation=enriched.workspace_operation,
                    explanation_mode=enriched.explanation_mode,
                    files_considered=enriched.files_considered,
                    files_read=files_read,
                )
        return enriched

    def _apply_search_chain(
        self,
        message: str,
        analysis: dict,
        tool_results: list,
        decision_report: ToolDecisionReport | None,
        dispatch_context: ExecutionDispatchContext | None,
    ) -> tuple[list, ToolDecisionReport | None]:
        """Chain read/explain after search_files when planned (P11-101–P11-104)."""
        plan = analysis.get("workspace_plan")
        if decision_report is None or plan is None:
            return tool_results, decision_report
        if not getattr(plan, "chain_after_search", False):
            return tool_results, decision_report
        if decision_report.workspace_operation != "search_then_read":
            return tool_results, decision_report

        search_result = next(
            (
                result
                for result in reversed(tool_results)
                if (getattr(result, "metadata", None) or {}).get("file_operation")
                == "search_files"
            ),
            None,
        )
        if search_result is None:
            return tool_results, decision_report

        params = parse_workspace_params(message)
        query = build_search_query(params)
        raw_results = extract_search_results(search_result)
        project_root = getattr(self.reasoning, "_project_root", None)
        if project_root is None:
            return tool_results, decision_report

        selection = select_strong_matches(raw_results, query, params, project_root)
        ambiguity_status = {
            "single_match": "clear",
            "multiple_matches": "ambiguous",
            "no_match": "no_match",
        }.get(selection.status, selection.status)
        decision_report = decision_report.with_workspace_context(
            workspace_operation=decision_report.workspace_operation,
            explanation_mode=decision_report.explanation_mode,
            files_considered=selection.strong_matches or selection.all_results,
            search_query=query.display,
            search_results=selection.all_results,
            selected_file=selection.selected_file,
            ambiguity_status=ambiguity_status,
            confidence=selection.confidence,
            reasoning_summary=selection.ambiguity_reason or decision_report.reasoning_summary,
        )

        if selection.status == "single_match" and selection.selected_file:
            read_results = self._run_tools(
                [read_tool_request(selection.selected_file)],
                dispatch_context,
                decision_report=decision_report,
            )
            decision_report = decision_report.with_workspace_context(
                workspace_operation=decision_report.workspace_operation,
                explanation_mode=decision_report.explanation_mode,
                files_considered=decision_report.files_considered,
                search_query=query.display,
                search_results=selection.all_results,
                selected_file=selection.selected_file,
                ambiguity_status="clear",
                confidence=selection.confidence,
            )
            return [*tool_results, *read_results], decision_report

        if selection.status == "multiple_matches":
            candidates = selection.strong_matches or selection.all_results
            return [
                *tool_results,
                ambiguity_tool_result(selection.ambiguity_reason, candidates),
            ], decision_report.with_workspace_context(
                workspace_operation=decision_report.workspace_operation,
                explanation_mode=decision_report.explanation_mode,
                files_considered=candidates,
                search_query=query.display,
                search_results=selection.all_results,
                ambiguity_status="ambiguous",
                confidence=selection.confidence,
            )

        return [
            *tool_results,
            no_match_tool_result(query.display),
        ], decision_report.with_workspace_context(
            workspace_operation=decision_report.workspace_operation,
            explanation_mode=decision_report.explanation_mode,
            search_query=query.display,
            search_results=(),
            ambiguity_status="no_match",
            confidence=0.0,
        )

    @staticmethod
    def _format_workspace_results(
        tool_results_text: str,
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> str:
        """Add workspace explanation guidance to prompt-ready tool output (P11-006)."""
        if decision_report is None or not decision_report.explanation_mode:
            return tool_results_text
        area_summary = ""
        plan = analysis.get("workspace_plan")
        if plan is not None:
            area_summary = getattr(plan, "area_summary", "") or ""
        return format_workspace_tool_results(
            tool_results_text,
            explanation_mode=decision_report.explanation_mode,
            area_summary=area_summary,
        )

    @staticmethod
    def _format_modification_results(
        tool_results_text: str,
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> str:
        """Attach modification plan summary to output (P11-306)."""
        if decision_report is None:
            return tool_results_text
        if decision_report.explanation_mode != "modification_plan":
            return tool_results_text
        plan_text = analysis.get("modification_plan_text", "")
        if not plan_text:
            plan = analysis.get("modification_plan")
            if plan is not None:
                plan_text = format_modification_plan_summary(plan)
        if not plan_text:
            return tool_results_text
        if tool_results_text.strip():
            return f"{plan_text}\n\n{tool_results_text}"
        return plan_text

    @staticmethod
    def _format_patch_application_results(
        tool_results_text: str,
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> str:
        """Attach patch application outcome to output (P12-006)."""
        if decision_report is None:
            return tool_results_text
        if not decision_report.patch_application_requested:
            return tool_results_text
        if decision_report.explanation_mode not in {
            "patch_application",
            None,
        } and not decision_report.patch_applied and not analysis.get(
            "patch_application_text",
        ):
            return tool_results_text

        patch_text = analysis.get("patch_application_text", "")
        if not patch_text:
            patch_result = analysis.get("patch_application_result")
            if patch_result is not None:
                patch_text = format_patch_application_summary(patch_result)
        if not patch_text:
            return tool_results_text
        if tool_results_text.strip():
            return f"{patch_text}\n\n{tool_results_text}"
        return patch_text

    @staticmethod
    def _format_rollback_results(
        tool_results_text: str,
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> str:
        """Attach rollback restore outcome to output (P12B2-005)."""
        if decision_report is None:
            return tool_results_text
        if decision_report.explanation_mode != "rollback":
            return tool_results_text

        rollback_text = analysis.get("rollback_text", "")
        if not rollback_text:
            rollback_result = analysis.get("rollback_result")
            if rollback_result is not None:
                from tools.decision.modification_guidance import format_rollback_summary

                rollback_text = format_rollback_summary(rollback_result)
        if not rollback_text:
            return tool_results_text
        if tool_results_text.strip():
            return f"{rollback_text}\n\n{tool_results_text}"
        return rollback_text

    def _run_multi_step_task(
        self,
        plan: TaskExecutionPlan,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
    ) -> tuple[list, object]:
        """Execute a multi-step task plan through ToolOrchestrator (P12B3-002, P128-002)."""
        engine = TaskExecutionEngine()
        enriched_dispatch = self._attach_decision_report(
            dispatch_context,
            decision_report,
        )
        report = engine.execute(
            plan,
            invoke=self._orchestrator_invoke(enriched_dispatch, decision_report),
            dispatch_context=enriched_dispatch,
        )
        return list(report.tool_results), report

    @staticmethod
    def _format_task_execution_results(
        tool_results_text: str,
        decision_report: ToolDecisionReport | None,
        analysis: dict,
    ) -> str:
        """Attach multi-step execution summary to output (P12B3-006)."""
        if decision_report is None or not decision_report.multi_step_execution:
            return tool_results_text
        report = analysis.get("task_execution_report")
        if report is None and decision_report.task_execution_result:
            raw = decision_report.task_execution_result
            steps = tuple(
                TaskExecutionStep.from_dict(item)
                for item in raw.get("steps", [])
            )
            report = TaskExecutionReport(
                objective=str(raw.get("objective", "")),
                steps=steps,
                steps_completed=int(raw.get("steps_completed", 0)),
                steps_failed=int(raw.get("steps_failed", 0)),
                total_duration_ms=float(raw.get("total_duration_ms", 0.0)),
                execution_summary=str(raw.get("execution_summary", "")),
                partial=bool(raw.get("partial", False)),
                unfinished_steps=tuple(raw.get("unfinished_steps", [])),
            )
        if report is None:
            return tool_results_text
        return format_task_execution_results(tool_results_text, report)

    def _plan_tools_override(self, requests: list[ToolRequest]) -> list[ToolRequest]:
        allowed = self.policy.clamp_tool_count(len(requests))
        truncated = len(requests) - allowed
        if truncated > 0:
            logger.info(
                "Tool dispatch truncated %d override requests (max=%d)",
                truncated,
                self.policy.max_tools,
            )
        return requests[:allowed]

    def _plan_tools(
        self,
        analysis: dict,
        planner_result,
    ) -> list[ToolRequest]:
        """Derive ordered tool requests from the Natural Language Planner."""
        requests = self.planner.to_tool_requests(planner_result)
        if not requests and analysis.get("needs_tool"):
            requests = self.executor.plan_tools(analysis)
        allowed = self.policy.clamp_tool_count(len(requests))
        truncated = len(requests) - allowed
        if truncated > 0:
            logger.info(
                "Tool dispatch truncated %d planned requests (max=%d)",
                truncated,
                self.policy.max_tools,
            )
        return requests[:allowed]

    def _run_agents(
        self,
        message: str,
        agent_context: AgentContext | None,
    ) -> list:
        return self.task_orchestrator.orchestrate(
            message,
            agent_context,
            max_agents=self.policy.max_agents,
        )

    def _orchestrator_invoke(
        self,
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
    ):
        """Build invoke callback routing through ToolOrchestrator (Phase 12.8)."""

        def invoke(request: ToolRequest) -> ToolResult:
            results = self.tool_orchestrator.orchestrate_requests(
                [request],
                dispatch_context=dispatch_context,
                decision_report=decision_report,
            )
            tool_results = self.tool_orchestrator.orchestration_results_to_tool_results(
                results,
            )
            if not tool_results:
                return ToolResult(
                    tool_name=request.tool_name,
                    success=False,
                    error="Aucun résultat retourné par l'orchestrateur.",
                    source="tool_orchestrator",
                )
            return tool_results[0]

        return invoke

    def _run_tools(
        self,
        requests: list[ToolRequest],
        dispatch_context: ExecutionDispatchContext | None,
        *,
        decision_report: ToolDecisionReport | None = None,
        message: str = "",
        planner_result=None,
    ) -> list:
        if decision_report is not None and (
            decision_report.fallback_action == FallbackAction.NO_CAPABILITY
        ):
            return [no_capability_tool_result(decision_report)]

        if decision_report is not None and (
            decision_report.fallback_action == FallbackAction.CLARIFICATION
        ):
            return [clarification_tool_result(decision_report)]

        if decision_report is not None and (
            decision_report.fallback_decision == FallbackDecision.REQUEST_CONFIRMATION.value
        ):
            return [fallback_confirmation_tool_result(decision_report)]

        if not requests and (
            planner_result is None or planner_result.total_steps == 0
        ):
            return []

        enriched_dispatch = self._attach_decision_report(dispatch_context, decision_report)
        if planner_result is not None and planner_result.total_steps > 0:
            orchestration_results = self.tool_orchestrator.orchestrate_plan(
                planner_result,
                message=message,
                dispatch_context=enriched_dispatch,
                decision_report=decision_report,
            )
        else:
            orchestration_results = self.tool_orchestrator.orchestrate_requests(
                requests,
                message=message,
                dispatch_context=enriched_dispatch,
                decision_report=decision_report,
            )
        return self.tool_orchestrator.orchestration_results_to_tool_results(
            orchestration_results,
        )

    @staticmethod
    def _attach_decision_report(
        dispatch_context: ExecutionDispatchContext | None,
        decision_report: ToolDecisionReport | None,
    ) -> ExecutionDispatchContext | None:
        if decision_report is None:
            return dispatch_context
        if dispatch_context is None:
            return ExecutionDispatchContext(
                user="Nolan",
                session_id="default",
                turn_id="default",
                decision_report=decision_report,
            )
        return ExecutionDispatchContext(
            user=dispatch_context.user,
            session_id=dispatch_context.session_id,
            turn_id=dispatch_context.turn_id,
            confirmed=dispatch_context.confirmed,
            confirmation_token=dispatch_context.confirmation_token,
            decision_report=decision_report,
        )

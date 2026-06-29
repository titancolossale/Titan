# =====================================
# Titan Execution Coordinator
# =====================================

"""Unified agent + tool dispatch with policy enforcement (Phase 8 — P8-062)."""

from __future__ import annotations

import logging

from agents.agent_context import AgentContext
from brain.decision_execution_bridge import (
    availability_resolver_from_manager,
    no_capability_tool_result,
)
from brain.executor import Executor
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from brain.tool_execution_bridge import ExecutionDispatchContext
from core.execution_policy import ExecutionPolicy
from core.execution_result import ExecutionResult
from core.task_orchestrator import TaskOrchestrator
from tools.decision.models import FallbackAction, ToolDecisionReport
from tools.tool_result import ToolRequest

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
    ) -> None:
        self.task_orchestrator = task_orchestrator
        self.tool_dispatcher = tool_dispatcher
        self.reasoning = reasoning or Reasoning()
        self.executor = executor or Executor()
        self.policy = policy or ExecutionPolicy()

    def execute(
        self,
        message: str,
        *,
        agent_context: AgentContext | None = None,
        dispatch_context: ExecutionDispatchContext | None = None,
        tool_requests_override: list[ToolRequest] | None = None,
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

        if tool_requests_override is not None:
            tool_requests = self._plan_tools_override(tool_requests_override)
        else:
            tool_requests = self._plan_tools(analysis)
        action_label = self.executor.execute(analysis)

        agent_results = self._run_agents(message, agent_context)
        tool_results = self._run_tools(
            tool_requests,
            dispatch_context,
            decision_report=decision_report,
        )

        return ExecutionResult(
            agent_results=agent_results,
            agent_results_text=self.task_orchestrator.format_results(agent_results),
            tool_results=tool_results,
            tool_results_text=self.tool_dispatcher.format_results(tool_results),
            action_label=action_label,
            decision_report=decision_report,
        )

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

    def _plan_tools(self, analysis: dict) -> list[ToolRequest]:
        requests = self.executor.plan_tools(analysis)
        allowed = self.policy.clamp_tool_count(len(requests))
        truncated = len(requests) - allowed
        if truncated > 0:
            logger.info(
                "Tool dispatch truncated %d requests (max=%d)",
                truncated,
                self.policy.max_tools,
            )
        return requests[:allowed]

    def _run_agents(
        self,
        message: str,
        agent_context: AgentContext | None,
    ) -> list:
        tasks = self.task_orchestrator.task_manager.create_tasks(message)
        allowed = self.policy.clamp_agent_count(len(tasks))
        if allowed < len(tasks):
            logger.info(
                "Agent pipeline truncated %d tasks (max=%d)",
                len(tasks) - allowed,
                self.policy.max_agents,
            )
            tasks = tasks[:allowed]

        results = []
        for agent_name, task in tasks:
            ctx = agent_context
            if ctx is not None:
                ctx = AgentContext(
                    user_message=ctx.user_message,
                    task=task,
                    current_user=ctx.current_user,
                    situational_context=ctx.situational_context,
                    retrieved_memory=ctx.retrieved_memory,
                    state=ctx.state,
                    mission=ctx.mission,
                    executive_analysis=ctx.executive_analysis,
                    active_project=ctx.active_project,
                    current_phase=ctx.current_phase,
                    current_goal=ctx.current_goal,
                )
            try:
                result = self.task_orchestrator.agent_manager.execute(
                    agent_name,
                    task,
                    ctx,
                )
            except Exception as exc:
                logger.error(
                    "Agent %s failed during execution: %s",
                    agent_name,
                    exc,
                    exc_info=True,
                )
                from agents.agent_result import AgentResult

                result = AgentResult(
                    agent_name=agent_name,
                    task=task,
                    summary=f"Erreur agent {agent_name}: {exc}",
                    confidence=0.0,
                )
            results.append(result)
        return results

    def _run_tools(
        self,
        requests: list[ToolRequest],
        dispatch_context: ExecutionDispatchContext | None,
        *,
        decision_report: ToolDecisionReport | None = None,
    ) -> list:
        if decision_report is not None and (
            decision_report.fallback_action == FallbackAction.NO_CAPABILITY
        ):
            return [no_capability_tool_result(decision_report)]

        if not requests:
            return []

        enriched_dispatch = self._attach_decision_report(dispatch_context, decision_report)
        return self.tool_dispatcher.dispatch(
            requests,
            dispatch_context=enriched_dispatch,
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

# =====================================
# Titan Tool Dispatcher
# =====================================

"""Brain-controlled tool dispatch with validation (Phase 6 — P6-031)."""

from __future__ import annotations

from brain.tool_execution_bridge import (
    ExecutionDispatchContext,
    build_tool_execution_context,
)
from tools.tool_manager import ToolManager
from tools.tool_policy import BRAIN_CALLER
from tools.tool_result import ToolRequest, ToolResult
from tools.tool_run_models import ToolRunStatus


class ToolDispatcher:
    """Validate and run tool requests from Brain reasoning/executor."""

    def __init__(self, tool_manager: ToolManager) -> None:
        self.tool_manager = tool_manager

    def dispatch(
        self,
        requests: list[ToolRequest],
        *,
        caller: str = BRAIN_CALLER,
        dispatch_context: ExecutionDispatchContext | None = None,
    ) -> list[ToolResult]:
        """Execute each request through ToolRuntime when v2 is active."""
        if not requests:
            return []

        runtime = self.tool_manager.runtime
        if runtime is not None:
            return self._dispatch_via_runtime(
                requests,
                caller=caller,
                dispatch_context=dispatch_context,
            )
        return self._dispatch_legacy(requests, caller=caller, dispatch_context=dispatch_context)

    def _dispatch_via_runtime(
        self,
        requests: list[ToolRequest],
        *,
        caller: str,
        dispatch_context: ExecutionDispatchContext | None,
    ) -> list[ToolResult]:
        runtime = self.tool_manager.runtime
        assert runtime is not None

        ctx = build_tool_execution_context(
            dispatch_context
            or ExecutionDispatchContext(
                user="Nolan",
                session_id="default",
                turn_id="default",
            ),
            caller=caller,
        )
        results: list[ToolResult] = []
        for request in requests:
            outcome = runtime.invoke(request.tool_name, request.params, ctx)
            result = runtime.outcome_to_result(outcome)
            if outcome.status == ToolRunStatus.QUEUED and outcome.run_id:
                polled = runtime.poll_run(outcome.run_id, timeout=0.0)
                if polled.result is not None:
                    result = runtime.outcome_to_result(polled)
            results.append(result)
        return results

    def _dispatch_legacy(
        self,
        requests: list[ToolRequest],
        *,
        caller: str,
        dispatch_context: ExecutionDispatchContext | None,
    ) -> list[ToolResult]:
        user = "Nolan"
        session_id = "default"
        turn_id = "default"
        if dispatch_context is not None:
            user = dispatch_context.user
            session_id = dispatch_context.session_id
            turn_id = dispatch_context.turn_id

        results: list[ToolResult] = []
        for request in requests:
            result = self.tool_manager.run(
                request.tool_name,
                request.params,
                caller=caller,
                user=user,
                session_id=session_id,
                turn_id=turn_id,
            )
            results.append(result)
        return results

    def probe_provider_health(self) -> str:
        """Probe providers and return prompt-ready health summary."""
        runtime = self.tool_manager.runtime
        if runtime is None:
            return ""
        return self.tool_manager.format_tool_status()

    @staticmethod
    def format_results(results: list[ToolResult]) -> str:
        """Produce prompt-ready text with per-tool source attribution."""
        if not results:
            return ""
        blocks = [result.format_for_prompt() for result in results]
        return "\n\n---\n\n".join(blocks)

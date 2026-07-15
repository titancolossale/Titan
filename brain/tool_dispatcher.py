# =====================================
# Titan Tool Dispatcher
# =====================================

"""Brain-controlled tool dispatch — formats results; execution via tool_executor (Phase 12.8)."""

from __future__ import annotations

from core.execution_context import ExecutionDispatchContext
from tools.tool_executor import execute_tool
from tools.tool_manager import ToolManager
from tools.tool_policy import BRAIN_CALLER
from tools.tool_result import ToolRequest, ToolResult


class ToolDispatcher:
    """Format tool results for Brain prompts.

    Direct execution is reserved for tests and TaskExecutionEngine invoke
    overrides. Production paths use ExecutionCoordinator → ToolOrchestrator.
    """

    def __init__(self, tool_manager: ToolManager) -> None:
        self.tool_manager = tool_manager

    def dispatch(
        self,
        requests: list[ToolRequest],
        *,
        caller: str = BRAIN_CALLER,
        dispatch_context: ExecutionDispatchContext | None = None,
    ) -> list[ToolResult]:
        """Execute each request through the unified tool executor."""
        if not requests:
            return []

        results: list[ToolResult] = []
        for request in requests:
            results.append(
                execute_tool(
                    self.tool_manager,
                    request.tool_name,
                    request.params,
                    caller=caller,
                    dispatch_context=dispatch_context,
                ),
            )
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

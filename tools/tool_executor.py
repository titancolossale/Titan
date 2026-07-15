# =====================================
# Titan Tool Executor
# =====================================

"""Single tool invocation path for orchestrator and dispatcher (Phase 12.8 — P128-002)."""

from __future__ import annotations

from core.execution_context import ExecutionDispatchContext, build_tool_execution_context
from tools.tool_manager import ToolManager
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus


def execute_tool(
    tool_manager: ToolManager,
    tool_name: str,
    params: dict | None,
    *,
    caller: str,
    dispatch_context: ExecutionDispatchContext | None = None,
    context: ToolExecutionContext | None = None,
) -> ToolResult:
    """Execute one tool through ToolRuntime when v2 is active, else legacy run."""
    ctx = context
    if ctx is None:
        ctx = build_tool_execution_context(
            dispatch_context
            or ExecutionDispatchContext(
                user="Nolan",
                session_id="default",
                turn_id="default",
            ),
            caller=caller,
        )

    runtime = tool_manager.runtime
    if runtime is not None:
        outcome = runtime.invoke(tool_name, params, ctx)
        result = runtime.outcome_to_result(outcome)
        if outcome.status == ToolRunStatus.QUEUED and outcome.run_id:
            polled = runtime.poll_run(outcome.run_id, timeout=0.0)
            if polled.result is not None:
                result = runtime.outcome_to_result(polled)
        return result

    return tool_manager.run(
        tool_name,
        params,
        caller=caller,
        user=ctx.user,
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
    )

# =====================================
# Titan Tool Execution Bridge
# =====================================

"""Bridge ThinkContext to ToolRuntime execution context (Phase 10A — P10A-025)."""

from __future__ import annotations

from dataclasses import dataclass

from brain.pipeline.context_bundle import ThinkContext
from tools.decision.execution_context import attach_decision_report
from tools.decision.models import ToolDecisionReport
from tools.tool_policy import BRAIN_CALLER
from tools.tool_run_models import ToolExecutionContext


@dataclass(frozen=True)
class ExecutionDispatchContext:
    """Per-turn dispatch metadata passed Brain → ExecutionCoordinator → ToolDispatcher."""

    user: str
    session_id: str
    turn_id: str
    confirmed: bool = False
    confirmation_token: str | None = None
    decision_report: ToolDecisionReport | None = None


def build_tool_execution_context(
    dispatch: ExecutionDispatchContext,
    *,
    caller: str = BRAIN_CALLER,
) -> ToolExecutionContext:
    """Convert dispatch context into a ToolRuntime ToolExecutionContext."""
    context = ToolExecutionContext(
        caller=caller,
        user=dispatch.user,
        session_id=dispatch.session_id,
        turn_id=dispatch.turn_id,
        confirmed=dispatch.confirmed,
        confirmation_token=dispatch.confirmation_token,
    )
    return attach_decision_report(context, dispatch.decision_report)


def dispatch_context_from_think(
    ctx: ThinkContext,
    *,
    conversation_session_id: str | None = None,
) -> ExecutionDispatchContext:
    """Build dispatch context from accumulated pipeline state."""
    session_id = ctx.session_id or conversation_session_id or "default"
    turn_id = ctx.turn_id or "default"
    return ExecutionDispatchContext(
        user=ctx.current_user,
        session_id=session_id,
        turn_id=turn_id,
        confirmed=ctx.tool_confirmed,
        confirmation_token=ctx.confirmation_token,
    )

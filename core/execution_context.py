# =====================================
# Titan Execution Context
# =====================================

"""Neutral dispatch context types shared by Brain, core, and tools (Phase 12.8 — P128-001)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.decision.execution_context import attach_decision_report
from tools.decision.models import ToolDecisionReport
from tools.tool_policy import BRAIN_CALLER
from tools.tool_run_models import ToolExecutionContext


@dataclass(frozen=True)
class ExecutionDispatchContext:
    """Per-turn dispatch metadata passed Brain → ExecutionCoordinator → tool stack."""

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

# =====================================
# Titan Tool Decision — Execution Context
# =====================================

"""DecisionReport propagation through ToolRuntime execution context (P10B-105)."""

from __future__ import annotations

from tools.decision.models import ToolDecisionReport
from tools.tool_run_models import ToolExecutionContext

DECISION_REPORT_METADATA_KEY = "decision_report"


def attach_decision_report(
    context: ToolExecutionContext,
    report: ToolDecisionReport | None,
) -> ToolExecutionContext:
    """Inject DecisionReport into execution context metadata."""
    if report is None:
        return context
    metadata = dict(context.metadata)
    metadata[DECISION_REPORT_METADATA_KEY] = report.to_dict()
    return ToolExecutionContext(
        caller=context.caller,
        user=context.user,
        session_id=context.session_id,
        turn_id=context.turn_id,
        confirmed=context.confirmed,
        confirmation_token=context.confirmation_token,
        dry_run=context.dry_run,
        execution_mode=context.execution_mode,
        metadata=metadata,
    )


def extract_decision_report(context: ToolExecutionContext) -> ToolDecisionReport | None:
    """Rehydrate DecisionReport from execution context metadata."""
    raw = context.metadata.get(DECISION_REPORT_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    return ToolDecisionReport.from_dict(raw)

# =====================================
# Titan Decision Execution Bridge
# =====================================

"""Canonical pipeline: Decision Engine → Execution Coordinator → Tool Runtime (P10B-106)."""

from __future__ import annotations

from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.execution_context import DECISION_REPORT_METADATA_KEY
from tools.decision.models import FallbackAction, ToolDecisionReport
from tools.tool_manager import ToolManager
from tools.tool_result import ToolResult

__all__ = [
    "DECISION_REPORT_METADATA_KEY",
    "availability_resolver_from_manager",
    "no_capability_tool_result",
]


def availability_resolver_from_manager(
    tool_manager: ToolManager,
) -> CapabilityAvailabilityResolver | None:
    """Build a live availability resolver when Tool Runtime V2 is active."""
    runtime = tool_manager.runtime
    if runtime is None:
        return None
    return CapabilityAvailabilityResolver(
        catalog=runtime.catalog,
        health_monitor=runtime.health_monitor,
        provider_registry=tool_manager.provider_registry,
    )


def no_capability_tool_result(report: ToolDecisionReport) -> ToolResult:
    """Surface NO_CAPABILITY to the user-facing execution flow (P10B-104)."""
    return ToolResult(
        tool_name=report.selected_tool or report.intent.value,
        success=False,
        error=(
            f"[Décision] Capacité indisponible — {report.decision_reason}. "
            "Aucun outil exécutable ne correspond à cette demande."
        ),
        source="decision_engine",
        metadata={
            "fallback_action": FallbackAction.NO_CAPABILITY.value,
            "decision_report": report.to_dict(),
        },
    )

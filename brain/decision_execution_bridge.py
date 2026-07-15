# =====================================
# Titan Decision Execution Bridge
# =====================================

"""Canonical pipeline: Decision Engine → Execution Coordinator → Tool Runtime (P10B-106)."""

from __future__ import annotations

from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.execution_context import DECISION_REPORT_METADATA_KEY
from tools.decision.models import FallbackAction, ToolDecisionReport
from tools.decision.provider_ranker import ProviderRanker
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.providers.provider_fallback_policy import ProviderFallbackPolicy
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.tool_manager import ToolManager
from tools.tool_result import ToolResult

__all__ = [
    "DECISION_REPORT_METADATA_KEY",
    "availability_resolver_from_manager",
    "decision_engine_from_manager",
    "performance_model_from_manager",
    "clarification_tool_result",
    "fallback_confirmation_tool_result",
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


def performance_model_from_manager(
    tool_manager: ToolManager,
) -> ProviderPerformanceModel | None:
    """Return the shared performance model when Tool Runtime V2 is active (P10B-1303)."""
    return tool_manager.performance_model


def decision_engine_from_manager(tool_manager: ToolManager) -> ToolDecisionEngine:
    """Build a decision engine wired to the manager's shared performance model (P10B-1304)."""
    performance_model = performance_model_from_manager(tool_manager)
    return ToolDecisionEngine(
        performance_model=performance_model,
        provider_ranker=ProviderRanker(performance_model=performance_model),
        fallback_policy=ProviderFallbackPolicy(performance_model=performance_model),
    )


def clarification_tool_result(report: ToolDecisionReport) -> ToolResult:
    """Surface CLARIFICATION to the user-facing execution flow (P10B-705)."""
    return ToolResult(
        tool_name=report.selected_tool or report.intent.value,
        success=False,
        error=(
            f"[Décision] Clarification requise — {report.decision_reason}. "
            "Précise ta demande pour que Titan choisisse le bon provider."
        ),
        source="decision_engine",
        metadata={
            "fallback_action": FallbackAction.CLARIFICATION.value,
            "decision_report": report.to_dict(),
        },
    )


def fallback_confirmation_tool_result(report: ToolDecisionReport) -> ToolResult:
    """Surface REQUEST_CONFIRMATION fallback policy to the user (P10B-905)."""
    return ToolResult(
        tool_name=report.selected_tool or report.intent.value,
        success=False,
        error=(
            f"[Politique de repli] Confirmation requise — {report.fallback_reason}. "
            "Confirme le changement de provider avant exécution."
        ),
        source="fallback_policy",
        metadata={
            "fallback_decision": report.fallback_decision,
            "fallback_policy": report.fallback_policy,
            "fallback_notice": (
                "Repli provider nécessite une confirmation utilisateur "
                "avant exécution."
            ),
            "decision_report": report.to_dict(),
        },
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


def provider_no_capability_tool_result(
    tool_name: str,
    error: str,
    *,
    execution_path: tuple[str, ...] = (),
) -> ToolResult:
    """Surface provider-layer NO_CAPABILITY (P10B-204)."""
    return ToolResult(
        tool_name=tool_name,
        success=False,
        error=f"[Provider] Capacité indisponible — {error}",
        source="provider_executor",
        metadata={
            "fallback_action": FallbackAction.NO_CAPABILITY.value,
            "no_capability": True,
            "execution_path": list(execution_path),
        },
    )

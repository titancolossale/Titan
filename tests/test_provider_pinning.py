# =====================================
# Titan Provider Pinning Tests
# =====================================

"""Tests for Phase 10B Batch 8 — Runtime Provider Pinning (P10B-801–P10B-806)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from brain.tool_execution_bridge import ExecutionDispatchContext, build_tool_execution_context
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport
from tools.health_monitor import HealthMonitor
from tools.providers.provider_executor import ProviderExecutionContext, ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    FallbackWebSearchProvider,
    StubWebSearchProvider,
)
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolRunStatus
from tools.web_search_tool import WebSearchTool


@pytest.fixture
def search_registry() -> ProviderRegistry:
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    registry.register(FallbackWebSearchProvider())
    return registry


@pytest.fixture
def search_executor(search_registry: ProviderRegistry) -> ProviderExecutor:
    return ProviderExecutor(registry=search_registry, health_monitor=HealthMonitor())


def _pinned_context(
    provider_id: str,
    *,
    allow_fallback: bool = False,
) -> ProviderExecutionContext:
    return ProviderExecutionContext(
        action="search",
        params={"query": "Titan"},
        execution_mode=ExecutionMode.MOCK,
        tool_name="web_search",
        pinned_provider=provider_id,
        planned_provider=provider_id,
        allow_fallback=allow_fallback,
    )


def test_pinned_provider_executes_selected_provider(
    search_executor: ProviderExecutor,
) -> None:
    """P10B-802: Runtime executes the Brain-pinned provider directly."""
    outcome = search_executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=_pinned_context("web_search"),
    )
    assert outcome.success
    assert outcome.provider_id == "web_search"
    assert outcome.execution_provider == "web_search"
    assert outcome.planned_provider == "web_search"
    assert outcome.execution_path == ("web_search",)
    assert outcome.fallback_used is False


def test_pinned_provider_does_not_reselect_when_primary_available(
    search_executor: ProviderExecutor,
) -> None:
    """P10B-802: No independent ranking when a valid pin is present."""
    outcome = search_executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=_pinned_context("web_search_fallback"),
    )
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"
    assert "web_search" not in outcome.execution_path


def test_unavailable_pinned_provider_returns_structured_error(
    search_registry: ProviderRegistry,
) -> None:
    """P10B-803: Unavailable pinned provider does not silently switch."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=_pinned_context("web_search", allow_fallback=False),
    )

    assert not outcome.success
    assert outcome.provider_unavailable is True
    assert outcome.no_capability is True
    assert outcome.original_provider == "web_search"
    assert outcome.provider_id == "web_search"
    assert outcome.execution_path == ("web_search",)
    assert outcome.replacement_provider is None
    assert "indisponible" in outcome.error.lower()


def test_fallback_allowed_runs_second_routing_pass(
    search_registry: ProviderRegistry,
) -> None:
    """P10B-804: Policy-enabled fallback performs a second routing pass."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=_pinned_context("web_search", allow_fallback=True),
    )

    assert outcome.success
    assert outcome.fallback_used is True
    assert outcome.original_provider == "web_search"
    assert outcome.replacement_provider == "web_search_fallback"
    assert outcome.provider_id == "web_search_fallback"
    assert outcome.execution_provider == "web_search_fallback"
    assert outcome.provider_changed is True
    assert outcome.fallback_reason


def test_fallback_denied_keeps_original_provider_metadata(
    search_registry: ProviderRegistry,
) -> None:
    """P10B-804: Fallback denied preserves original provider in structured response."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=_pinned_context("web_search", allow_fallback=False),
    )

    assert outcome.fallback_used is False
    assert outcome.replacement_provider is None
    assert outcome.original_provider == "web_search"


def test_health_transition_between_planning_and_execution(
    search_registry: ProviderRegistry,
) -> None:
    """P10B-806: Health change after planning blocks pinned execution safely."""
    monitor = HealthMonitor()
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    ctx = _pinned_context("web_search", allow_fallback=False)
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ctx,
    )

    assert not outcome.success
    assert outcome.provider_unavailable is True
    assert outcome.planned_provider == "web_search"


def test_decision_report_enriched_with_pinning_fields() -> None:
    """P10B-805: DecisionReport includes execution and fallback provider fields."""
    report = ToolDecisionReport(
        intent=Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        selected_provider="web_search",
        planned_provider="web_search",
    )
    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": "web_search_fallback",
            "provider_score": 80.0,
            "provider_health": "online",
            "provider_version": "0.1.0",
            "execution_path": ["web_search", "web_search_fallback"],
            "execution_provider": "web_search_fallback",
            "planned_provider": "web_search",
            "provider_changed": True,
            "provider_change_reason": "health monitor state offline",
            "fallback_used": True,
            "fallback_reason": "health monitor state offline",
            "original_provider": "web_search",
            "replacement_provider": "web_search_fallback",
        },
    )
    assert enriched is not None
    assert enriched.planned_provider == "web_search"
    assert enriched.execution_provider == "web_search_fallback"
    assert enriched.provider_changed is True
    assert enriched.fallback_used is True
    assert enriched.original_provider == "web_search"
    assert enriched.replacement_provider == "web_search_fallback"


def test_runtime_injects_pinned_provider_into_context(tmp_path: Path) -> None:
    """P10B-801: ToolRuntime passes selected_provider as pinned_provider."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    runtime = manager.runtime
    assert runtime is not None

    report = ToolDecisionReport(
        intent=Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        selected_provider="web_search",
        planned_provider="web_search",
    )
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        decision_report=report,
    )
    ctx = build_tool_execution_context(dispatch)
    outcome = runtime.invoke("web_search", {"query": "Titan"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.metadata.get("provider_id") == "web_search"
    assert outcome.result.metadata.get("execution_provider") == "web_search"
    assert outcome.result.metadata.get("planned_provider") == "web_search"


def test_legacy_unpinned_executor_still_ranks_providers(
    search_registry: ProviderRegistry,
) -> None:
    """Backward compatibility: unpinned execution keeps legacy ranked fallback."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"


def test_legacy_runtime_without_decision_report(
    tmp_path: Path,
    mock_agent_llm: MagicMock,
) -> None:
    """Backward compatibility: legacy runtime path still executes."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=False)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())

    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success


def test_web_search_tool_honors_pinned_provider(
    search_executor: ProviderExecutor,
) -> None:
    """Pinned provider flows through WebSearchTool to ProviderExecutor."""
    tool = WebSearchTool(provider_executor=search_executor)
    result = tool.run(
        query="Titan",
        _execution_context={
            "pinned_provider": "web_search_fallback",
            "planned_provider": "web_search_fallback",
            "execution_mode": ExecutionMode.MOCK.value,
            "allow_fallback": False,
        },
    )
    assert result.success
    assert result.metadata.get("provider_id") == "web_search_fallback"
    assert result.metadata.get("execution_provider") == "web_search_fallback"


def test_decision_report_roundtrip_includes_pinning_fields() -> None:
    """Serialization preserves provider pinning metadata."""
    report = ToolDecisionReport(
        intent=Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        selected_provider="web_search",
        planned_provider="web_search",
        execution_provider="web_search_fallback",
        provider_changed=True,
        provider_change_reason="offline",
        fallback_used=True,
        fallback_reason="offline",
        original_provider="web_search",
        replacement_provider="web_search_fallback",
    )
    restored = ToolDecisionReport.from_dict(report.to_dict())
    assert restored.planned_provider == "web_search"
    assert restored.execution_provider == "web_search_fallback"
    assert restored.provider_changed is True
    assert restored.replacement_provider == "web_search_fallback"

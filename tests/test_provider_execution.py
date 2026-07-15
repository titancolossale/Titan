# =====================================
# Titan Provider Execution Tests
# =====================================

"""Integration tests for Phase 10B Batch 3 — Provider Execution (P10B-201–P10B-206)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.models import ToolDecisionReport
from tools.health_monitor import HealthMonitor
from tools.providers.provider_dashboard import build_dashboard_snapshot
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    FallbackWebSearchProvider,
    FailingWebSearchProvider,
    StubWebSearchProvider,
)
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.web_search_tool import WebSearchTool


@pytest.fixture
def provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    registry.register(FallbackWebSearchProvider())
    return registry


@pytest.fixture
def provider_executor(provider_registry: ProviderRegistry) -> ProviderExecutor:
    return ProviderExecutor(
        registry=provider_registry,
        health_monitor=HealthMonitor(),
    )


def test_provider_metadata_exposed(provider_registry: ProviderRegistry) -> None:
    """P10B-202: Registry exposes complete provider metadata."""
    meta = provider_registry.get_metadata("web_search")
    assert meta is not None
    assert meta.provider_name == "web_search"
    assert meta.version == "0.1.0"
    assert "web_search" in meta.capabilities
    assert "search" in meta.supported_actions
    assert meta.health == ToolHealthState.ONLINE
    assert meta.execution_mode == ExecutionMode.LIVE.value

    all_meta = provider_registry.list_metadata()
    assert len(all_meta) >= 1
    assert all_meta[0].to_dict()["provider_name"]


def test_provider_selection_via_registry(provider_executor: ProviderExecutor) -> None:
    """P10B-201: ProviderExecutor selects provider through registry only."""
    outcome = provider_executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "web_search"
    assert outcome.provider_score > 0


def test_provider_health_degradation_skips_offline(
    provider_registry: ProviderRegistry,
) -> None:
    """P10B-204: Offline primary provider skips to fallback."""
    registry = provider_registry
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "fallback test"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"
    assert "web_search_fallback" in outcome.execution_path


def test_provider_fallback_on_execution_failure(
    provider_registry: ProviderRegistry,
) -> None:
    """P10B-204: Failed primary provider falls back to next compatible."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(FailingWebSearchProvider())
    registry.register(FallbackWebSearchProvider())
    executor = ProviderExecutor(registry=registry, health_monitor=HealthMonitor())

    outcome = executor.execute(
        "search",
        {"query": "retry"},
        capability="web_search",
    )
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"
    assert outcome.retry_count >= 1
    assert len(outcome.execution_path) >= 2


def test_provider_unavailable_returns_no_capability() -> None:
    """P10B-204: No compatible provider returns canonical NO_CAPABILITY."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "nothing"},
        capability="web_search",
    )
    assert not outcome.success
    assert outcome.no_capability


def test_provider_telemetry_records_execution(
    provider_executor: ProviderExecutor,
) -> None:
    """P10B-203: Telemetry captures provider execution details."""
    ctx = provider_executor.registry  # noqa: F841 — ensure registry wired
    outcome = provider_executor.execute(
        "search",
        {"query": "telemetry"},
        capability="web_search",
        context=__import__(
            "tools.providers.provider_executor",
            fromlist=["ProviderExecutionContext"],
        ).ProviderExecutionContext(
            action="search",
            params={"query": "telemetry"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            runtime_id="run-123",
            decision_id="dec-456",
        ),
    )
    assert outcome.success
    records = provider_executor.telemetry.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.provider_selected == "web_search"
    assert record.decision_id == "dec-456"
    assert record.runtime_id == "run-123"
    assert record.success is True
    assert record.provider_version == "0.1.0"
    assert record.duration_ms >= 0


def test_decision_report_enrichment() -> None:
    """P10B-205: DecisionReport enriched with provider execution metadata."""
    report = ToolDecisionReport(
        intent=__import__("tools.decision.intent", fromlist=["Intent"]).Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=__import__("tools.tool_enums", fromlist=["RiskLevel"]).RiskLevel.LOW,
        confirmation_required=False,
    )
    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": "web_search",
            "provider_score": 110.0,
            "provider_health": "online",
            "provider_version": "0.1.0",
            "execution_path": ["web_search"],
        },
    )
    assert enriched is not None
    assert enriched.selected_provider == "web_search"
    assert enriched.provider_score == 110.0
    assert enriched.provider_health == "online"
    assert enriched.provider_version == "0.1.0"
    assert enriched.execution_path == ("web_search",)


def test_dashboard_inspection_model(
    provider_registry: ProviderRegistry,
    provider_executor: ProviderExecutor,
) -> None:
    """P10B-206: Dashboard snapshot is serializable."""
    provider_executor.execute(
        "search",
        {"query": "dashboard"},
        capability="web_search",
    )
    snapshot = build_dashboard_snapshot(
        provider_registry.list_metadata(),
        provider_executor.telemetry,
    )
    assert "providers" in snapshot
    assert "recent_executions" in snapshot
    assert "generated_at" in snapshot
    assert len(snapshot["providers"]) >= 1
    assert len(snapshot["recent_executions"]) >= 1


def test_web_search_tool_uses_provider_executor(
    provider_executor: ProviderExecutor,
) -> None:
    """P10B-201: WebSearchTool routes through ProviderExecutor."""
    tool = WebSearchTool(provider_executor=provider_executor)
    result = tool.run(query="Titan AI")
    assert result.success
    assert result.metadata.get("provider_id") == "web_search"


def test_runtime_web_search_execution(tmp_path: Path) -> None:
    """P10B-201/203: ToolRuntime executes web_search via provider layer."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    runtime = manager.runtime
    assert runtime is not None
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = runtime.invoke("web_search", {"query": "Titan"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.success
    assert outcome.result.metadata.get("provider_id") == "web_search"


def test_coordinator_enriches_decision_report(
    tmp_path: Path,
    mock_agent_llm: MagicMock,
) -> None:
    """P10B-205: ExecutionCoordinator enriches DecisionReport after provider run."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())

    result = coordinator.execute("Search the latest NQ news")
    assert result.decision_report is not None
    assert result.decision_report.selected_tool == "web_search"
    assert result.decision_report.selected_provider == "web_search"
    assert result.decision_report.provider_version == "0.1.0"
    assert result.decision_report.decision_id


def test_legacy_runtime_still_executes(
    tmp_path: Path,
    mock_agent_llm: MagicMock,
) -> None:
    """Backward compatibility: legacy runtime path still works."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=False)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())

    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success
    assert manager.runtime is None


def test_tool_manager_dashboard_export(tmp_path: Path) -> None:
    """P10B-206: ToolManager exposes dashboard export."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    manager.run("web_search", {"query": "export test"}, caller="test")
    snapshot = manager.export_provider_dashboard()
    assert snapshot["providers"]
    assert isinstance(snapshot, dict)

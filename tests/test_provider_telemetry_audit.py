# =====================================
# Titan Provider Telemetry & Audit Tests
# =====================================

"""Tests for Phase 10B Batch 10 — Provider Fallback Telemetry & Audit (P10B-1001–P10B-1006)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.adapters.legacy_tool_adapter import register_legacy_tools
from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.audit.tool_audit_models import ToolAuditEvent
from tools.capability_catalog import CapabilityCatalog
from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.models import ToolDecisionReport
from tools.dependency_resolver import DependencyResolver
from tools.health_monitor import HealthMonitor
from tools.providers.provider_dashboard import build_dashboard_snapshot
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.provider_telemetry import ProviderTelemetryCollector
from tools.providers.web_search_provider import (
    FallbackWebSearchProvider,
    FailingWebSearchProvider,
    StubWebSearchProvider,
)
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_runtime import ToolRuntime
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


def test_audit_event_provider_fallback_fields() -> None:
    """P10B-1001: ToolAuditEvent includes provider fallback telemetry fields."""
    event = ToolAuditEvent.build(
        event_type="provider_executed",
        run_id="run-abc",
        tool_name="web_search",
        provider_name="web_search",
        provider_health="online",
        fallback_used=True,
        fallback_reason="primary offline",
        retry_count=2,
        decision_id="dec-xyz",
        latency_ms=45.2,
        execution_mode="mock",
        success=True,
    )
    data = event.to_dict()
    assert data["provider_name"] == "web_search"
    assert data["fallback_used"] is True
    assert data["retry_count"] == 2
    assert data["decision_id"] == "dec-xyz"
    assert data["latency_ms"] == 45.2
    restored = ToolAuditEvent.from_dict(data)
    assert restored.fallback_reason == "primary offline"


def test_audit_event_legacy_compat_missing_new_fields() -> None:
    """P10B-1001: Legacy audit JSON loads without new provider fields."""
    legacy = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event_type": "completed",
        "run_id": "run-legacy",
        "tool_name": "time",
        "schema_version": 1,
    }
    event = ToolAuditEvent.from_dict(legacy)
    assert event.provider_name == ""
    assert event.fallback_used is False
    assert event.retry_count == 0
    assert event.decision_id == ""


def test_telemetry_collector_aggregates_success_and_failure(
    provider_executor: ProviderExecutor,
) -> None:
    """P10B-1002: Collector tracks usage, failures, latency, and success rate."""
    provider_executor.execute(
        "search",
        {"query": "ok"},
        capability="web_search",
    )
    provider_executor.execute(
        "search",
        {"query": "fail"},
        capability="web_search",
    )
    snapshot = provider_executor.telemetry.snapshot()
    stats = provider_executor.telemetry.get_provider_stats("web_search")
    assert snapshot.total_executions >= 1
    assert stats.usage_count >= 1
    assert 0.0 <= stats.success_rate <= 1.0
    assert stats.average_latency_ms >= 0


def test_telemetry_collector_fallback_and_retries() -> None:
    """P10B-1002: Collector aggregates fallback and retry counts."""
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
    assert outcome.fallback_used

    snapshot = executor.telemetry.snapshot()
    assert snapshot.total_fallbacks >= 1
    assert snapshot.total_retries >= 1


def test_telemetry_health_transition(provider_executor: ProviderExecutor) -> None:
    """P10B-1002: Health transitions are recorded."""
    collector = provider_executor.telemetry
    collector.record_health_transition(
        "web_search",
        "online",
        "degraded",
        reason="rate_limit",
    )
    snapshot = collector.snapshot()
    assert len(snapshot.health_transitions) == 1
    assert snapshot.health_transitions[0].to_state == "degraded"


def test_telemetry_snapshot_api(provider_executor: ProviderExecutor) -> None:
    """P10B-1003: ProviderTelemetrySnapshot exports serializable aggregate."""
    provider_executor.execute("search", {"query": "snap"}, capability="web_search")
    payload = provider_executor.telemetry.snapshot().to_dict()
    assert "generated_at" in payload
    assert "provider_stats" in payload
    assert "recent_records" in payload
    assert payload["total_executions"] >= 1


def test_decision_report_telemetry_references() -> None:
    """P10B-1004: DecisionReport exposes telemetry record references."""
    report = ToolDecisionReport(
        intent=__import__("tools.decision.intent", fromlist=["Intent"]).Intent.WEB_SEARCH,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": "web_search",
            "provider_score": 100.0,
            "provider_health": "online",
            "provider_version": "0.1.0",
            "execution_path": ["web_search"],
            "retry_count": 1,
            "telemetry_record_index": 3,
            "telemetry_snapshot_at": "2026-06-29T12:00:00+00:00",
        },
    )
    assert enriched is not None
    assert enriched.retry_count == 1
    assert enriched.telemetry_record_index == 3
    assert enriched.telemetry_snapshot_at == "2026-06-29T12:00:00+00:00"


def test_runtime_records_telemetry_and_audit(tmp_path: Path) -> None:
    """P10B-1005: Runtime records telemetry and enriched provider audit."""
    audit_path = tmp_path / "audit.jsonl"
    audit_logger = ToolAuditLogger(enabled=True, file_path=audit_path)
    reg = ToolRegistry()
    catalog = CapabilityCatalog()
    resolver = DependencyResolver()
    runtime = ToolRuntime(
        registry=reg,
        policy=ToolPolicy(),
        catalog=catalog,
        dependency_resolver=resolver,
        audit_logger=audit_logger,
    )
    assert runtime.provider_executor is not None
    reg.register(WebSearchTool(provider_executor=runtime.provider_executor))
    register_legacy_tools(reg, catalog, resolver)
    runtime.refresh_catalog()
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = runtime.invoke("web_search", {"query": "telemetry audit"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.metadata.get("telemetry_record_index") is not None
    assert runtime.provider_executor is not None
    assert len(runtime.provider_executor.telemetry.list_records()) >= 1

    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    provider_events = [
        json.loads(line)
        for line in lines
        if json.loads(line).get("event_type") == "provider_executed"
    ]
    assert provider_events
    last = provider_events[-1]
    assert last["provider_name"] == "web_search"
    assert "latency_ms" in last
    assert last["execution_mode"] == "mock"


def test_dashboard_telemetry_metadata(
    provider_registry: ProviderRegistry,
    provider_executor: ProviderExecutor,
) -> None:
    """P10B-1006: Dashboard export includes visualization-ready telemetry metadata."""
    provider_executor.execute("search", {"query": "dash"}, capability="web_search")
    snapshot = build_dashboard_snapshot(
        provider_registry.list_metadata(),
        provider_executor.telemetry,
    )
    assert "telemetry_summary" in snapshot
    assert "telemetry_metadata" in snapshot
    metadata = snapshot["telemetry_metadata"]
    assert metadata["schema"] == "titan.provider_telemetry.v1"
    assert "chart_hints" in metadata
    assert snapshot["telemetry_summary"]["total_executions"] >= 1


def test_provider_offline_records_failure_telemetry() -> None:
    """P10B-1002: Offline provider contributes failure telemetry."""
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    registry.register(FallbackWebSearchProvider())
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=registry, health_monitor=monitor)

    outcome = executor.execute("search", {"query": "offline"}, capability="web_search")
    assert outcome.success
    assert outcome.provider_id == "web_search_fallback"
    snapshot = executor.telemetry.snapshot()
    assert snapshot.total_executions >= 1


def test_tool_manager_telemetry_snapshot_export(tmp_path: Path) -> None:
    """P10B-1003: ToolManager exposes telemetry snapshot API."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    from tools.tool_enums import ExecutionMode
    from tools.tool_run_models import ToolExecutionContext

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    manager.runtime.invoke("web_search", {"query": "export"}, ctx)
    payload = manager.export_provider_telemetry_snapshot()
    assert payload["total_executions"] >= 1


def test_legacy_runtime_still_executes_without_telemetry_crash(
    tmp_path: Path,
    mock_agent_llm: MagicMock,
) -> None:
    """Backward compatibility: legacy runtime path unaffected by telemetry layer."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=False)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())

    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success


def test_audit_persistence_jsonl(tmp_path: Path) -> None:
    """P10B-1001: Enriched audit events persist to JSONL."""
    audit_path = tmp_path / "tools_audit.jsonl"
    logger = ToolAuditLogger(file_path=audit_path, enabled=True)
    logger.log(
        ToolAuditEvent.build(
            event_type="provider_executed",
            run_id="run-persist",
            tool_name="web_search",
            provider_name="web_search_fallback",
            fallback_used=True,
            retry_count=1,
        )
    )
    payload = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert payload["fallback_used"] is True
    assert payload["schema_version"] == 2

# =====================================
# Titan Performance Runtime Wiring Tests
# =====================================

"""Tests for Phase 10B Batch 13 — Performance-Aware Runtime Wiring (P10B-1301–P10B-1306)."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.brain import Brain
from brain.decision_execution_bridge import (
    decision_engine_from_manager,
    performance_model_from_manager,
)
from brain.reasoning import Reasoning
from agents.agent_manager import AgentManager
from context.context_manager import ContextManager
from core.execution_coordinator import ExecutionCoordinator
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from core.task_orchestrator import TaskOrchestrator
from brain.tool_dispatcher import ToolDispatcher
from core.task_manager import TaskManager as CoreTaskManager
from memory.memory_service import MemoryService
from memory.memory_manager import MemoryManager
from memory.long_term_memory import LongTermMemory
from tools.decision import ToolDecisionEngine
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.provider_ranker import ProviderRanker
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.providers.provider_telemetry import ProviderExecutionRecord, ProviderTelemetryCollector
from tools.providers.telemetry_persistence import TelemetryPersistenceManager
from tools.tool_enums import ExecutionMode
from tools.tool_manager import ToolManager
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_runtime import ToolRuntime


def _sample_record(
    *,
    provider: str = "web_search",
    runtime_id: str = "run-perf",
    duration_ms: float = 50.0,
    success: bool = True,
) -> ProviderExecutionRecord:
    return ProviderExecutionRecord(
        provider_selected=provider,
        duration_ms=duration_ms,
        provider_health="online",
        provider_version="0.1.0",
        success=success,
        retry_count=0,
        decision_id="dec-1",
        runtime_id=runtime_id,
        tool_name="web_search",
    )


@pytest.fixture
def tmp_path_local(tmp_path: Path) -> Path:
    return tmp_path


def test_runtime_injects_performance_model_on_startup(tmp_path_local: Path) -> None:
    """P10B-1301: ToolRuntime composition root creates ProviderPerformanceModel."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    assert manager.runtime is not None
    model = manager.runtime.performance_model
    assert model is not None
    assert isinstance(model, ProviderPerformanceModel)
    assert model.collector is manager.provider_executor.telemetry


def test_tool_manager_shares_performance_model_with_runtime(tmp_path_local: Path) -> None:
    """P10B-1303: ToolManager exposes the same instance as ToolRuntime."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    assert manager.performance_model is manager.runtime.performance_model
    assert manager.performance_model is not None


def test_provider_ranker_uses_shared_model(tmp_path_local: Path) -> None:
    """P10B-1303: ProviderRanker from ToolManager binds shared performance model."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    ranker = manager.provider_ranker()
    assert ranker.performance_model is manager.performance_model


def test_startup_reload_restores_performance_scores(tmp_path_local: Path) -> None:
    """P10B-1302: Persisted telemetry reload drives performance metrics on startup."""
    telemetry_path = tmp_path_local / "provider_telemetry.json"
    collector = ProviderTelemetryCollector()
    for index in range(5):
        collector.record(
            _sample_record(
                runtime_id=f"run-{index}",
                duration_ms=2000.0,
                success=False,
            ),
        )
    persistence = TelemetryPersistenceManager(
        file_path=telemetry_path,
        persist=True,
    )
    persistence.save_snapshot(collector)

    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    manager.runtime.telemetry_path = telemetry_path
    manager.runtime.telemetry_persistence = persistence
    manager.runtime.persist_telemetry = True
    manager.runtime.telemetry_persistence.reload_on_startup(
        manager.provider_executor.telemetry,
    )
    manager.runtime.wire_performance_model()

    metrics = manager.performance_model.get_metrics("web_search")
    assert metrics.sample_count == 5
    assert metrics.performance_score < 50.0


def test_multiple_restarts_preserve_performance(tmp_path_local: Path) -> None:
    """P10B-1302: Performance model reflects telemetry across simulated restarts."""
    telemetry_path = tmp_path_local / "telemetry.json"
    manager_a = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    manager_a.runtime.telemetry_path = telemetry_path
    manager_a.runtime.telemetry_persistence = TelemetryPersistenceManager(
        file_path=telemetry_path,
        persist=True,
    )
    manager_a.runtime.persist_telemetry = True

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="restart",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    manager_a.runtime.invoke("web_search", {"query": "restart perf"}, ctx)

    manager_b = ToolManager(
        project_root=tmp_path_local,
        registry=manager_a.registry,
        policy=manager_a.policy,
        provider_registry=manager_a.provider_registry,
        runtime=None,
        use_runtime_v2=True,
        register_defaults=False,
    )
    manager_b.runtime.telemetry_path = telemetry_path
    manager_b.runtime.telemetry_persistence = TelemetryPersistenceManager(
        file_path=telemetry_path,
        persist=True,
    )
    manager_b.runtime.persist_telemetry = True
    manager_b.runtime.telemetry_persistence.reload_on_startup(
        manager_b.provider_executor.telemetry,
    )
    manager_b.runtime.wire_performance_model()

    assert len(manager_b.provider_executor.telemetry.list_records()) >= 1
    snapshot = manager_b.export_provider_performance_snapshot()
    assert len(snapshot["providers"]) >= 1


def test_decision_engine_from_manager_uses_shared_model(tmp_path_local: Path) -> None:
    """P10B-1304: Decision engine DI uses ToolManager performance model."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    engine = decision_engine_from_manager(manager)
    assert engine.performance_model is manager.performance_model
    assert engine.provider_ranker.performance_model is manager.performance_model


def test_performance_model_from_manager_none_without_runtime(tmp_path_local: Path) -> None:
    """P10B-1304: Legacy path without runtime returns None performance model."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=False)
    assert performance_model_from_manager(manager) is None
    engine = decision_engine_from_manager(manager)
    assert engine.performance_model is None


def test_brain_wires_decision_engine_from_tool_manager(tmp_path_local: Path) -> None:
    """P10B-1304: Brain composition root wires shared performance model."""
    tools = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    brain = Brain(
        agent_manager=AgentManager(),
        context_manager=ContextManager(
            state_manager=StateManager(),
            mission_manager=MissionManager(),
        ),
        state_manager=StateManager(),
        mission_manager=MissionManager(),
        memory_service=MemoryService(
            short_term=MemoryManager(),
            long_term=LongTermMemory(),
        ),
        tool_manager=tools,
    )
    assert brain.reasoning.decision_engine.performance_model is tools.performance_model


def test_export_provider_performance_snapshot(tmp_path_local: Path) -> None:
    """P10B-1305: ToolManager exposes ProviderPerformanceSnapshot API."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    manager.provider_executor.telemetry.record(_sample_record())
    manager.runtime.wire_performance_model()

    snapshot = manager.export_provider_performance_snapshot()
    assert "generated_at" in snapshot
    assert len(snapshot["providers"]) == 1
    assert snapshot["providers"][0]["provider_id"] == "web_search"


def test_export_performance_analytics_metadata(tmp_path_local: Path) -> None:
    """P10B-1306: Dashboard metadata exported without UI."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    metadata = manager.export_provider_performance_analytics_metadata()
    assert metadata["schema"] == "titan.provider_performance.v1"
    assert "chart_hints" in metadata
    assert "export_provider_performance_snapshot" in metadata["query_apis"]

    dashboard = manager.export_provider_dashboard()
    assert "performance_metadata" in dashboard


def test_ranking_uses_reloaded_performance(tmp_path_local: Path) -> None:
    """P10B-1303: Provider ranking reflects reloaded historical performance."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    collector = manager.provider_executor.telemetry
    for _ in range(6):
        collector.record(
            _sample_record(duration_ms=3000.0, success=False),
        )
    manager.runtime.wire_performance_model()

    engine = decision_engine_from_manager(manager)
    resolver = CapabilityAvailabilityResolver(
        catalog=manager.runtime.catalog,
        health_monitor=manager.runtime.health_monitor,
        provider_registry=manager.provider_registry,
    )
    report = engine.decide(
        "Latest Nvidia news",
        availability_resolver=resolver,
    )
    assert report.performance_score is not None
    assert report.performance_score < 50.0


def test_telemetry_invalidation_after_execution(tmp_path_local: Path) -> None:
    """P10B-1301: Performance cache invalidates after runtime records telemetry."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    model = manager.performance_model
    assert model is not None
    model.get_metrics("web_search")
    assert "web_search" in model._cache

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="inv",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = manager.runtime.invoke("web_search", {"query": "invalidate"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert "web_search" not in model._cache


def test_legacy_compatibility_without_performance_model(tmp_path_local: Path) -> None:
    """Legacy runtime v1 path unchanged when performance model absent."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=False)
    assert manager.performance_model is None
    ranker = ProviderRanker()
    assert ranker.performance_model is None
    engine = ToolDecisionEngine()
    report = engine.decide("Quelle heure est-il ?")
    assert report.performance_score is None


def test_execution_coordinator_regression_with_wired_reasoning(
    tmp_path_local: Path,
) -> None:
    """Regression: ExecutionCoordinator works with DI-wired Reasoning."""
    manager = ToolManager(project_root=tmp_path_local, use_runtime_v2=True)
    reasoning = Reasoning(decision_engine=decision_engine_from_manager(manager))
    agent_manager = AgentManager()
    orchestrator = TaskOrchestrator(CoreTaskManager(agent_manager), agent_manager)
    dispatcher = ToolDispatcher(manager)
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=reasoning)
    result = coordinator.execute("Quelle heure est-il ?")
    assert result.action_label
    assert not result.tool_results or all(
        getattr(item, "success", False) or getattr(item, "error", "")
        for item in result.tool_results
    )


def test_injected_performance_model_preserved(tmp_path_local: Path) -> None:
    """P10B-1304: Explicit DI injection is not overwritten."""
    collector = ProviderTelemetryCollector()
    injected = ProviderPerformanceModel(collector=collector)
    runtime = ToolRuntime(
        registry=ToolRegistry(),
        policy=ToolPolicy(),
        performance_model=injected,
    )
    runtime.wire_performance_model()
    assert runtime.performance_model is injected

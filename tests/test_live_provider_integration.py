# =====================================
# Titan Live Provider Integration Tests
# =====================================

"""Tests for Phase 10B Batch 14 — Live Provider Integration Closure (P10B-1401–P10B-1407)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.decision_execution_bridge import (
    availability_resolver_from_manager,
    decision_engine_from_manager,
)
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager as CoreTaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision.models import FallbackAction
from tools.providers.brave_http_client import HttpResponse, MockHttpTransport
from tools.providers.brave_search_provider import BraveSearchProvider
from tools.providers.credential_manager import CredentialManager
from tools.providers.github_provider import LiveGitHubProvider
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_executor import ProviderExecutionContext, ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.provider_telemetry import ProviderExecutionRecord
from tools.providers.web_search_provider import StubWebSearchProvider
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus

_VALID_BRAVE_KEY = "BSA-test-key-abcdefghijklmnopqrstuvwxyz"
_VALID_GITHUB_TOKEN = "ghp_testtoken1234567890123456789012345678"
_GITHUB_BASE = "https://api.github.com"


def _brave_env() -> dict[str, str | None]:
    return {"TITAN_BRAVE_SEARCH_API_KEY": _VALID_BRAVE_KEY}


def _github_env() -> dict[str, str | None]:
    return {"TITAN_GITHUB_TOKEN": _VALID_GITHUB_TOKEN}


def _web_success_body() -> str:
    return json.dumps(
        {
            "web": {
                "results": [
                    {
                        "title": "Titan AI Project",
                        "url": "https://example.com/titan",
                        "description": "Agentic AI system.",
                    },
                ],
            },
        },
    )


def _github_user_body() -> str:
    return json.dumps({"login": "nolan", "id": 1})


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.py").write_text("# settings\n", encoding="utf-8")
    (tmp_path / "sample.py").write_text("print('titan')\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def brave_registry() -> ProviderRegistry:
    credential_manager = CredentialManager(env=_brave_env())
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=200,
                body=_web_success_body(),
            ),
        },
    )
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("brave_search"),
    )
    registry.register(
        BraveSearchProvider(context=context, http_transport=transport),
    )
    registry.register(StubWebSearchProvider())
    return registry


@pytest.fixture
def github_registry() -> ProviderRegistry:
    credential_manager = CredentialManager(env=_github_env())
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    transport = MockHttpTransport(
        responses={
            f"{_GITHUB_BASE}/user": HttpResponse(
                status_code=200,
                body=_github_user_body(),
            ),
        },
    )
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("github"),
    )
    registry.register(
        LiveGitHubProvider(context=context, http_transport=transport),
    )
    return registry


def _manager(project_root: Path, registry: ProviderRegistry | None = None) -> ToolManager:
    kwargs: dict = {"project_root": project_root, "use_runtime_v2": True}
    if registry is not None:
        kwargs["provider_registry"] = registry
    return ToolManager(**kwargs)


def _coordinator(manager: ToolManager, mock_agent_llm: MagicMock) -> ExecutionCoordinator:
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(CoreTaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    return ExecutionCoordinator(
        orchestrator,
        ToolDispatcher(manager),
        reasoning=Reasoning(decision_engine=decision_engine_from_manager(manager)),
    )


def test_provider_health_synced_on_startup(project_root: Path) -> None:
    """P10B-1402: ToolManager syncs provider health into HealthMonitor on startup."""
    manager = _manager(project_root)
    runtime = manager.runtime
    assert runtime is not None
    for provider_id in ("file_system", "brave_search", "github"):
        state = runtime.health_monitor.get_provider_health(provider_id)
        assert state != ToolHealthState.UNKNOWN


def test_executor_receives_performance_model_on_wire(project_root: Path) -> None:
    """P10B-1403: wire_performance_model binds ProviderExecutor.performance_model."""
    manager = _manager(project_root)
    assert manager.runtime.performance_model is not None
    assert manager.provider_executor.performance_model is manager.runtime.performance_model


def test_brave_full_decision_runtime_performance_loop(
    project_root: Path,
    brave_registry: ProviderRegistry,
) -> None:
    """P10B-1404: BraveSearch through decision → runtime → telemetry → performance."""
    manager = _manager(project_root, brave_registry)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(
        "Recherche web : dernières actualités Titan AI",
        availability_resolver=resolver,
    )
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL
    assert report.selected_tool == "web_search"
    assert report.selected_provider == "brave_search"
    assert report.provider_health is not None
    assert report.performance_score is not None
    assert report.fallback_decision

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="b14-brave",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"decision_report": report.to_dict(), "execution_mode_override": True},
    )
    outcome = manager.runtime.invoke("web_search", {"query": "Titan AI"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.metadata.get("provider_id") == "brave_search"

    metrics = manager.performance_model.get_metrics("brave_search")
    assert metrics.sample_count >= 1


def test_github_full_decision_runtime_performance_loop(
    project_root: Path,
    github_registry: ProviderRegistry,
) -> None:
    """P10B-1405: GitHub through decision → runtime → telemetry → performance."""
    manager = _manager(project_root, github_registry)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(
        "GitHub list commits for repository titan-org/Titan",
        availability_resolver=resolver,
    )
    from tools.decision.models import enrich_github_decision_context

    report = enrich_github_decision_context(
        report,
        github_operation="list_commits",
        repository="titan-org/Titan",
        execution_mode="mock",
    )
    assert report.selected_tool == "github"
    assert report.selected_provider == "github"
    assert report.github_operation is not None
    assert report.performance_score is not None

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="b14-github",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"decision_report": report.to_dict(), "execution_mode_override": True},
    )
    outcome = manager.runtime.invoke(
        "github",
        {"action": "get_authenticated_user"},
        ctx,
    )
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result.metadata.get("provider_id") == "github"
    assert manager.performance_model.get_metrics("github").sample_count >= 1


def test_filesystem_full_decision_runtime_performance_loop(
    project_root: Path,
) -> None:
    """P10B-1406: FileSystem through decision → runtime → telemetry → performance."""
    manager = _manager(project_root)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(
        "Lire le fichier config/settings.py",
        availability_resolver=resolver,
    )
    from tools.decision.models import enrich_file_decision_context

    report = enrich_file_decision_context(
        report,
        target_path="config/settings.py",
        execution_mode="live",
    )
    assert report.selected_tool == "file_read"
    assert report.selected_provider == "file_system"
    assert report.file_operation == "read_file"
    assert report.target_path == "config/settings.py"

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="b14-fs",
        turn_id="t1",
        execution_mode=ExecutionMode.LIVE,
        metadata={"decision_report": report.to_dict()},
    )
    outcome = manager.runtime.invoke(
        "file_read",
        {"path": "config/settings.py"},
        ctx,
    )
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result.metadata.get("provider_id") == "file_system"
    assert manager.performance_model.get_metrics("file_system").sample_count >= 1


def test_telemetry_updates_performance_ranking(
    project_root: Path,
    brave_registry: ProviderRegistry,
) -> None:
    """P10B-1403: Post-execution telemetry invalidates and refreshes performance scores."""
    manager = _manager(project_root, brave_registry)
    collector = manager.provider_executor.telemetry
    for index in range(5):
        collector.record(
            ProviderExecutionRecord(
                provider_selected="web_search",
                duration_ms=4000.0,
                provider_health="degraded",
                provider_version="0.1.0",
                success=False,
                retry_count=1,
                decision_id=f"dec-{index}",
                runtime_id=f"run-{index}",
                tool_name="web_search",
            ),
        )
    manager.runtime.wire_performance_model()
    stub_score = manager.performance_model.get_metrics("web_search").performance_score
    assert stub_score < 50.0

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="rank",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    manager.runtime.invoke("web_search", {"query": "rank test"}, ctx)
    manager.runtime.wire_performance_model()
    brave_metrics = manager.performance_model.get_metrics("brave_search")
    assert brave_metrics.sample_count >= 1


def test_fallback_prefers_better_performance_provider(
    brave_registry: ProviderRegistry,
    project_root: Path,
) -> None:
    """P10B-1407: Runtime fallback routing uses performance-aware provider ordering."""
    manager = _manager(project_root, brave_registry)
    collector = manager.provider_executor.telemetry
    for _ in range(6):
        collector.record(
            ProviderExecutionRecord(
                provider_selected="brave_search",
                duration_ms=5000.0,
                provider_health="degraded",
                provider_version="1.0.0",
                success=False,
                retry_count=2,
                decision_id="dec-bad",
                runtime_id="run-bad",
                tool_name="web_search",
            ),
        )
    for _ in range(3):
        collector.record(
            ProviderExecutionRecord(
                provider_selected="web_search",
                duration_ms=40.0,
                provider_health="online",
                provider_version="0.1.0",
                success=True,
                retry_count=0,
                decision_id="dec-good",
                runtime_id="run-good",
                tool_name="web_search",
            ),
        )
    manager.runtime.wire_performance_model()

    executor = ProviderExecutor(
        registry=brave_registry,
        health_monitor=manager.runtime.health_monitor,
        performance_model=manager.performance_model,
    )
    ranked = brave_registry.select_providers(
        "search",
        ExecutionMode.MOCK,
        capability="web_search",
        health_monitor=manager.runtime.health_monitor,
        performance_model=manager.performance_model,
    )
    baseline = brave_registry.select_providers(
        "search",
        ExecutionMode.MOCK,
        capability="web_search",
        health_monitor=manager.runtime.health_monitor,
        performance_model=None,
    )
    assert len(ranked) >= 2
    provider_ids = [item[0] for item in ranked]
    assert "brave_search" in provider_ids
    assert "web_search" in provider_ids
    perf_scores = dict(ranked)
    base_scores = dict(baseline)
    assert perf_scores["web_search"] - perf_scores["brave_search"] > (
        base_scores["web_search"] - base_scores["brave_search"]
    )

    transport = MockHttpTransport(
        responses={
            "https://api.search.brave.com/res/v1/web/search": HttpResponse(
                status_code=429,
                body='{"message":"rate limit"}',
            ),
        },
    )
    provider = brave_registry.get("brave_search")
    assert isinstance(provider, BraveSearchProvider)
    provider._http = transport  # noqa: SLF001 — test injection

    outcome = executor.execute(
        "search",
        {"query": "fallback perf"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "fallback perf"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
        ),
    )
    assert outcome.success
    assert outcome.fallback_used
    assert outcome.provider_id == "web_search"
    assert "brave_search" in outcome.execution_path


def test_coordinator_enriches_decision_report_with_execution_metadata(
    project_root: Path,
    brave_registry: ProviderRegistry,
    mock_agent_llm: MagicMock,
) -> None:
    """P10B-1404: ExecutionCoordinator enriches DecisionReport after live provider run."""
    manager = _manager(project_root, brave_registry)
    coordinator = _coordinator(manager, mock_agent_llm)
    result = coordinator.execute("Recherche web : Titan agentic AI news")
    report = result.decision_report
    assert report is not None
    assert report.selected_tool == "web_search"
    assert report.selected_provider == "brave_search"
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success
    if report.execution_provider:
        assert report.provider_latency_ms is not None
        assert report.provider_health


def test_regression_existing_performance_wiring_tests(project_root: Path) -> None:
    """Regression: Batch 13 performance wiring remains intact."""
    manager = _manager(project_root)
    assert manager.performance_model is manager.runtime.performance_model
    engine = decision_engine_from_manager(manager)
    assert engine.provider_ranker.performance_model is manager.performance_model
    assert engine.fallback_policy.performance_model is manager.performance_model

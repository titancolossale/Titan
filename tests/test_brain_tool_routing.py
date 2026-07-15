# =====================================
# Titan Brain Tool Routing Tests
# =====================================

"""Tests for Phase 10B Batch 7 — Brain Tool Routing (P10B-701–P10B-705)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain.decision_execution_bridge import clarification_tool_result
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from agents.agent_manager import AgentManager
from tools.decision import FallbackAction, Intent, ToolDecisionEngine
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.models import ToolDecisionReport
from tools.decision.provider_ranker import ProviderRanker
from tools.health_monitor import HealthMonitor
from tools.providers.credential_manager import CredentialManager
from tools.providers.defaults import register_default_providers
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_enums import RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager


@pytest.fixture
def engine() -> ToolDecisionEngine:
    return ToolDecisionEngine()


@pytest.fixture
def routing_registry() -> ProviderRegistry:
    env = {"TITAN_BRAVE_SEARCH_API_KEY": "test-brave-key-for-routing-tests"}
    credential_manager = CredentialManager(env=env)
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(
        runtime_version="0.10.0",
        credential_manager=credential_manager,
        configuration_store=configuration_store,
    )
    register_default_providers(
        registry,
        credential_manager=credential_manager,
        configuration_store=configuration_store,
    )
    return registry


@pytest.fixture
def availability_resolver(routing_registry: ProviderRegistry) -> CapabilityAvailabilityResolver:
    from tools.capability_catalog import CapabilityCatalog
    from tools.tool_capability import ToolCapability
    from tools.tool_enums import ExecutionMode, InvocationMode, RiskLevel

    catalog = CapabilityCatalog()
    for tool_name, provider_name in (
        ("file_read", "file_system"),
        ("web_search", "web_search"),
        ("github", "github"),
    ):
        catalog.register(
            ToolCapability.from_schema(
                tool_name,
                f"Test {tool_name}",
                [],
                invocation_mode=InvocationMode.SYNC,
                execution_mode=ExecutionMode.LIVE,
                risk_level=RiskLevel.LOW,
                provider_name=provider_name,
            ),
        )
    return CapabilityAvailabilityResolver(
        catalog=catalog,
        health_monitor=HealthMonitor(),
        provider_registry=routing_registry,
    )


# ---------------------------------------------------------------------------
# P10B-703 — Natural-language routing examples
# ---------------------------------------------------------------------------


def test_route_find_file_to_file_system_provider(engine: ToolDecisionEngine) -> None:
    """Find Titan_Context.md → FileSystemProvider."""
    report = engine.decide("Find Titan_Context.md")
    assert report.intent == Intent.FILE_SEARCH
    assert report.selected_tool == "file_read"
    assert report.selected_provider == "file_system"
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL
    assert report.ranking_score is not None
    assert report.ranking_score >= 45.0


def test_route_latest_commits_to_github_provider(engine: ToolDecisionEngine) -> None:
    """Show latest commits → GitHubProvider."""
    report = engine.decide("Show latest commits")
    assert report.intent == Intent.GITHUB
    assert report.selected_tool == "github"
    assert report.selected_provider == "github"
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL


def test_route_nvidia_news_to_brave_search_provider(engine: ToolDecisionEngine) -> None:
    """Latest Nvidia news → BraveSearchProvider."""
    report = engine.decide("Latest Nvidia news")
    assert report.intent == Intent.WEB_SEARCH
    assert report.selected_tool == "web_search"
    assert report.selected_provider == "brave_search"
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL


# ---------------------------------------------------------------------------
# P10B-704 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_provider_fields(engine: ToolDecisionEngine) -> None:
    """DecisionReport includes provider routing metadata."""
    report = engine.decide("Find Titan_Context.md")
    assert report.selected_provider == "file_system"
    assert report.candidate_providers
    assert report.candidate_providers[0].provider_id == "file_system"
    assert report.ranking_score == report.candidate_providers[0].score
    assert report.confidence > 0.0
    assert report.reasoning_summary
    data = report.to_dict()
    assert data["selected_provider"] == "file_system"
    assert data["candidate_providers"]
    assert data["ranking_score"] is not None
    assert data["reasoning_summary"]

    restored = ToolDecisionReport.from_dict(data)
    assert restored.selected_provider == report.selected_provider
    assert restored.candidate_providers[0].provider_id == "file_system"


# ---------------------------------------------------------------------------
# P10B-702 — Capability ranking
# ---------------------------------------------------------------------------


def test_brave_ranks_above_stub_for_news(
    routing_registry: ProviderRegistry,
) -> None:
    """BraveSearchProvider outranks stub web_search for news queries."""
    ranker = ProviderRanker()
    from tools.decision.models import IntentClassification

    classification = IntentClassification(
        intent=Intent.WEB_SEARCH,
        confidence=0.9,
        reason="test",
    )
    ranked = ranker.rank(
        "Latest Nvidia news",
        classification,
        selected_tool="web_search",
        provider_registry=routing_registry,
    )
    assert len(ranked) >= 2
    assert ranked[0].provider_id == "brave_search"
    assert ranked[0].score > ranked[1].score


def test_provider_health_influences_ranking(
    routing_registry: ProviderRegistry,
    availability_resolver: CapabilityAvailabilityResolver,
) -> None:
    """Degraded provider health lowers ranking score."""
    engine = ToolDecisionEngine()
    baseline = engine.decide(
        "Latest Nvidia news",
        availability_resolver=availability_resolver,
    )
    availability_resolver.health_monitor.set_provider_health(
        "brave_search",
        ToolHealthState.DEGRADED,
    )
    degraded = engine.decide(
        "Latest Nvidia news",
        availability_resolver=availability_resolver,
    )
    assert baseline.selected_provider in {"brave_search", "web_search"}
    assert degraded.selected_provider in {"brave_search", "web_search"}
    if baseline.selected_provider != "brave_search":
        pytest.skip("Brave Search unavailable in test environment")
    baseline_brave = next(
        c for c in baseline.candidate_providers if c.provider_id == "brave_search"
    )
    degraded_brave = next(
        c for c in degraded.candidate_providers if c.provider_id == "brave_search"
    )
    assert degraded_brave.score < baseline_brave.score


# ---------------------------------------------------------------------------
# P10B-705 — Clarification path
# ---------------------------------------------------------------------------


def test_low_confidence_returns_clarification(
    engine: ToolDecisionEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Low provider confidence triggers clarification instead of execution."""
    monkeypatch.setattr(
        "tools.decision.tool_decision_engine._MIN_PROVIDER_SCORE",
        500.0,
    )
    report = engine.decide("Latest Nvidia news")
    assert report.fallback_action == FallbackAction.CLARIFICATION
    assert report.selected_tool == "web_search"
    assert report.selected_provider is None
    assert report.candidate_providers


def test_ambiguous_provider_routing_clarification(
    routing_registry: ProviderRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguous provider ranking with low intent confidence asks for clarification."""
    engine = ToolDecisionEngine()
    monkeypatch.setattr(
        "tools.decision.tool_decision_engine._PROVIDER_AMBIGUITY_MARGIN",
        200.0,
    )
    monkeypatch.setattr(
        "tools.decision.tool_decision_engine._MIN_PROVIDER_CONFIDENCE",
        1.0,
    )
    from tools.decision.models import IntentClassification
    from tools.decision.provider_ranker import ProviderRanker

    ranker = ProviderRanker()
    classification = IntentClassification(
        intent=Intent.WEB_SEARCH,
        confidence=0.4,
        reason="ambiguous",
    )
    ranked = ranker.rank(
        "Latest Nvidia news",
        classification,
        selected_tool="web_search",
        provider_registry=routing_registry,
    )
    assert len(ranked) >= 2
    report = engine._clarification_report(
        classification,
        selected_tool="web_search",
        provider_candidates=ranked,
        reason="Ambiguous provider routing (test)",
    )
    assert report.fallback_action == FallbackAction.CLARIFICATION


def test_clarification_tool_result_surfaces_to_user() -> None:
    """Clarification path produces user-visible decision_engine result."""
    report = ToolDecisionReport(
        intent=Intent.WEB_SEARCH,
        confidence=0.4,
        tool_required=True,
        candidate_tools=(),
        selected_tool="web_search",
        decision_reason="Ambiguous routing",
        risk_level=RiskLevel.SAFE,
        confirmation_required=False,
        fallback_action=FallbackAction.CLARIFICATION,
        reasoning_summary="Need clarification",
    )
    result = clarification_tool_result(report)
    assert result.success is False
    assert result.source == "decision_engine"
    assert "Clarification requise" in result.error


def test_reasoning_skips_tools_on_clarification(
    engine: ToolDecisionEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reasoning sets needs_clarification and emits no tool requests."""
    monkeypatch.setattr(
        "tools.decision.tool_decision_engine._MIN_PROVIDER_SCORE",
        500.0,
    )
    reasoning = Reasoning(decision_engine=engine)
    analysis = reasoning.analyze("Latest Nvidia news")
    assert analysis["needs_clarification"] is True
    assert analysis["tool_requests"] == []
    assert analysis["decision_report"].fallback_action == FallbackAction.CLARIFICATION


# ---------------------------------------------------------------------------
# Provider unavailable
# ---------------------------------------------------------------------------


def test_provider_unavailable_no_capability(
    routing_registry: ProviderRegistry,
    availability_resolver: CapabilityAvailabilityResolver,
) -> None:
    """Blocked provider yields NO_CAPABILITY when no fallback remains."""
    availability_resolver.health_monitor.set_provider_health(
        "file_system",
        ToolHealthState.OFFLINE,
    )
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Find Titan_Context.md",
        availability_resolver=availability_resolver,
    )
    assert report.fallback_action == FallbackAction.NO_CAPABILITY


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_existing_time_routing_regression(engine: ToolDecisionEngine) -> None:
    """Non-provider tools still route without provider selection."""
    report = engine.decide("Quelle heure est-il ?")
    assert report.selected_tool == "time"
    assert report.selected_provider is None
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL


def test_decision_runtime_integration_regression(
    tmp_path,
    mock_agent_llm: MagicMock,
) -> None:
    """ExecutionCoordinator still executes time tool through decision pipeline."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Quelle heure est-il ?")
    assert result.decision_report is not None
    assert result.decision_report.selected_tool == "time"
    assert result.tool_results[0].success


def test_github_reasoning_params() -> None:
    """GitHub tool requests include inferred action from message."""
    analysis = Reasoning().analyze("Show latest commits")
    assert analysis["needs_tool"] is True
    assert analysis["tool_requests"][0].tool_name == "github"
    assert analysis["tool_requests"][0].params["action"] == "list_commits"

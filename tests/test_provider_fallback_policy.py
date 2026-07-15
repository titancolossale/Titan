# =====================================
# Titan Provider Fallback Policy Tests
# =====================================

"""Tests for Phase 10B Batch 9 — Provider Fallback Policy (P10B-901–P10B-906)."""

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
from tools.decision.intent import Intent
from tools.decision.models import FallbackAction, ToolDecisionReport
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.health_monitor import HealthMonitor
from tools.providers.provider_executor import ProviderExecutionContext, ProviderExecutor
from tools.providers.provider_fallback_policy import (
    FallbackDecision,
    FallbackEvaluationContext,
    ProviderFallbackPolicy,
    ProviderFallbackPolicyConfig,
    format_fallback_user_notice,
)
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import FallbackWebSearchProvider, StubWebSearchProvider
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager


@pytest.fixture
def search_registry() -> ProviderRegistry:
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(StubWebSearchProvider())
    registry.register(FallbackWebSearchProvider())
    return registry


@pytest.fixture
def search_executor(search_registry: ProviderRegistry) -> ProviderExecutor:
    return ProviderExecutor(registry=search_registry, health_monitor=HealthMonitor())


def _policy(**overrides: object) -> ProviderFallbackPolicy:
    config = ProviderFallbackPolicyConfig(
        allow_provider_fallback=bool(overrides.get("allow_provider_fallback", False)),
        allow_cross_provider=bool(overrides.get("allow_cross_provider", True)),
        allow_retry=bool(overrides.get("allow_retry", True)),
        fallback_timeout=float(overrides.get("fallback_timeout", 30.0)),
    )
    return ProviderFallbackPolicy(config=config)


def _ctx(**overrides: object) -> FallbackEvaluationContext:
    return FallbackEvaluationContext(
        provider_id=str(overrides.get("provider_id", "web_search")),
        capability=str(overrides.get("capability", "web_search")),
        execution_mode=overrides.get("execution_mode", ExecutionMode.MOCK),
        provider_health=overrides.get("provider_health", ToolHealthState.ONLINE),
        confirmation_required=bool(overrides.get("confirmation_required", False)),
        user_confirmed=bool(overrides.get("user_confirmed", False)),
        risk_level=overrides.get("risk_level", RiskLevel.LOW),
    )


def test_healthy_provider_allows_fallback_when_enabled() -> None:
    """P10B-901: Healthy provider with fallback enabled."""
    outcome = _policy(allow_provider_fallback=True).evaluate(_ctx())
    assert outcome.decision == FallbackDecision.ALLOW_FALLBACK
    assert outcome.policy


def test_healthy_provider_denies_fallback_when_disabled() -> None:
    outcome = _policy(allow_provider_fallback=False).evaluate(_ctx())
    assert outcome.decision == FallbackDecision.DENY_FALLBACK


def test_offline_provider_retry_when_degraded() -> None:
    """P10B-902: Degraded provider triggers RETRY_ORIGINAL."""
    outcome = _policy(allow_retry=True).evaluate(
        _ctx(provider_health=ToolHealthState.DEGRADED),
    )
    assert outcome.decision == FallbackDecision.RETRY_ORIGINAL


def test_offline_provider_allows_cross_provider_fallback() -> None:
    outcome = _policy(allow_provider_fallback=True).evaluate(
        _ctx(provider_health=ToolHealthState.OFFLINE),
    )
    assert outcome.decision == FallbackDecision.ALLOW_FALLBACK
    assert "cross-provider" in outcome.reason


def test_offline_provider_denies_fallback_when_disabled() -> None:
    outcome = _policy(allow_provider_fallback=False).evaluate(
        _ctx(provider_health=ToolHealthState.OFFLINE),
    )
    assert outcome.decision == FallbackDecision.DENY_FALLBACK


def test_offline_provider_aborts_when_retry_and_fallback_disabled() -> None:
    outcome = _policy(
        allow_provider_fallback=False,
        allow_retry=False,
    ).evaluate(_ctx(provider_health=ToolHealthState.OFFLINE))
    assert outcome.decision == FallbackDecision.ABORT


def test_live_mode_cross_provider_requires_confirmation() -> None:
    outcome = _policy(allow_provider_fallback=True).evaluate(
        _ctx(
            provider_health=ToolHealthState.OFFLINE,
            execution_mode=ExecutionMode.LIVE,
            confirmation_required=True,
        ),
    )
    assert outcome.decision == FallbackDecision.REQUEST_CONFIRMATION


def test_retry_failure_then_escalates_to_fallback(
    search_registry: ProviderRegistry,
) -> None:
    """After retry failure, policy escalates to cross-provider fallback when allowed."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "Titan"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            pinned_provider="web_search",
            planned_provider="web_search",
            fallback_decision=FallbackDecision.RETRY_ORIGINAL.value,
            allow_fallback=True,
        ),
    )
    assert outcome.success
    assert outcome.fallback_used is True
    assert outcome.replacement_provider == "web_search_fallback"


def test_retry_success_on_healthy_provider(
    search_executor: ProviderExecutor,
) -> None:
    """RETRY_ORIGINAL on available provider executes without fallback."""
    outcome = search_executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "Titan"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            pinned_provider="web_search",
            planned_provider="web_search",
            fallback_decision=FallbackDecision.RETRY_ORIGINAL.value,
        ),
    )
    assert outcome.success
    assert outcome.fallback_used is False


def test_retry_failure_then_fallback_allowed(
    search_registry: ProviderRegistry,
) -> None:
    """After retry failure, ALLOW_FALLBACK performs second routing pass."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "Titan"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            pinned_provider="web_search",
            planned_provider="web_search",
            fallback_decision=FallbackDecision.ALLOW_FALLBACK.value,
            allow_fallback=True,
        ),
    )
    assert outcome.success
    assert outcome.fallback_used is True
    assert outcome.replacement_provider == "web_search_fallback"


def test_fallback_denied_by_policy_at_runtime(
    search_registry: ProviderRegistry,
) -> None:
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "Titan"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            pinned_provider="web_search",
            planned_provider="web_search",
            fallback_decision=FallbackDecision.DENY_FALLBACK.value,
            allow_fallback=False,
        ),
    )
    assert not outcome.success
    assert outcome.fallback_used is False
    notice = format_fallback_user_notice(
        outcome,
        fallback_decision=FallbackDecision.DENY_FALLBACK.value,
    )
    assert "Repli refusé par la politique" in notice


def test_fallback_executed_user_notice() -> None:
    from tools.providers.provider_executor import ProviderExecutionResult

    outcome = ProviderExecutionResult(
        success=True,
        provider_id="web_search_fallback",
        fallback_used=True,
        original_provider="web_search",
        replacement_provider="web_search_fallback",
    )
    notice = format_fallback_user_notice(outcome)
    assert "web_search" in notice
    assert "FallbackWebSearchProvider" in notice


def test_decision_report_includes_fallback_policy_fields() -> None:
    """P10B-903: DecisionReport enriched with fallback policy metadata."""
    engine = ToolDecisionEngine(
        fallback_policy=_policy(allow_provider_fallback=True),
    )
    report = engine.decide("recherche web Titan AI")
    assert report.selected_tool == "web_search"
    assert report.fallback_policy
    assert report.fallback_decision
    assert report.fallback_reason

    payload = report.to_dict()
    assert "fallback_policy" in payload
    assert "fallback_decision" in payload
    restored = ToolDecisionReport.from_dict(payload)
    assert restored.fallback_decision == report.fallback_decision


def test_brain_routing_surfaces_confirmation_required() -> None:
    engine = ToolDecisionEngine(
        fallback_policy=_policy(allow_provider_fallback=True),
    )
    report = engine._apply_fallback_policy(
        ToolDecisionReport(
            intent=Intent.WEB_SEARCH,
            confidence=0.9,
            tool_required=True,
            candidate_tools=(),
            selected_tool="web_search",
            decision_reason="test",
            risk_level=RiskLevel.HIGH,
            confirmation_required=True,
            fallback_action=FallbackAction.EXECUTE_TOOL,
            selected_provider="web_search",
            planned_provider="web_search",
            provider_health=ToolHealthState.OFFLINE.value,
            execution_mode=ExecutionMode.LIVE.value,
        ),
        selected_tool="web_search",
        risk_level=RiskLevel.HIGH,
        confirmation_required=True,
    )
    assert report.fallback_decision == FallbackDecision.REQUEST_CONFIRMATION.value


def test_legacy_allow_fallback_without_decision(
    search_registry: ProviderRegistry,
) -> None:
    """Backward compatibility: allow_fallback bool without fallback_decision."""
    monitor = HealthMonitor()
    monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    executor = ProviderExecutor(registry=search_registry, health_monitor=monitor)

    outcome = executor.execute(
        "search",
        {"query": "Titan"},
        capability="web_search",
        context=ProviderExecutionContext(
            action="search",
            params={"query": "Titan"},
            execution_mode=ExecutionMode.MOCK,
            tool_name="web_search",
            pinned_provider="web_search",
            planned_provider="web_search",
            allow_fallback=True,
        ),
    )
    assert outcome.success
    assert outcome.fallback_used is True


def test_runtime_injects_fallback_decision_from_report(tmp_path: Path) -> None:
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
        fallback_decision=FallbackDecision.ALLOW_FALLBACK.value,
        fallback_policy="fallback+cross_provider+retry",
    )
    params = runtime._inject_execution_context(
        {"query": "Titan"},
        run_id="run-1",
        context=None,
        decision_report=report,
    )
    exec_ctx = params["_execution_context"]
    assert exec_ctx["fallback_decision"] == FallbackDecision.ALLOW_FALLBACK.value
    assert exec_ctx["allow_fallback"] is True
    assert exec_ctx["fallback_policy"] == "fallback+cross_provider+retry"


def test_regression_coordinator_time_tool(
    tmp_path: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(
        orchestrator,
        dispatcher,
        reasoning=Reasoning(),
    )
    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success

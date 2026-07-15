# =====================================
# Titan Provider Performance Model Tests
# =====================================

"""Tests for Phase 10B Batch 12 — Telemetry-Driven Provider Optimization (P10B-1201–P10B-1206)."""

from __future__ import annotations

import pytest

from tools.decision import Intent, ToolDecisionEngine
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.models import IntentClassification, ToolDecisionReport
from tools.decision.provider_ranker import ProviderRanker
from tools.health_monitor import HealthMonitor
from tools.providers.credential_manager import CredentialManager
from tools.providers.defaults import register_default_providers
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_fallback_policy import (
    FallbackDecision,
    FallbackEvaluationContext,
    ProviderFallbackPolicy,
    ProviderFallbackPolicyConfig,
)
from tools.providers.provider_performance_model import (
    ProviderPerformanceModel,
    ProviderPerformanceWeights,
)
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.provider_telemetry import ProviderExecutionRecord, ProviderTelemetryCollector
from tools.tool_enums import ExecutionMode, ToolHealthState


def _record(
    provider: str,
    *,
    success: bool = True,
    duration_ms: float = 50.0,
    retry_count: int = 0,
) -> ProviderExecutionRecord:
    return ProviderExecutionRecord(
        provider_selected=provider,
        duration_ms=duration_ms,
        provider_health="online",
        provider_version="0.1.0",
        success=success,
        retry_count=retry_count,
        decision_id="dec-test",
        runtime_id="run-test",
        tool_name="web_search",
    )


def _seed_collector(
    collector: ProviderTelemetryCollector,
    provider: str,
    *,
    count: int,
    success: bool = True,
    duration_ms: float = 50.0,
    retry_count: int = 0,
) -> None:
    for _ in range(count):
        collector.record(
            _record(
                provider,
                success=success,
                duration_ms=duration_ms,
                retry_count=retry_count,
            ),
        )


@pytest.fixture
def collector() -> ProviderTelemetryCollector:
    return ProviderTelemetryCollector()


@pytest.fixture
def performance_model(collector: ProviderTelemetryCollector) -> ProviderPerformanceModel:
    return ProviderPerformanceModel(
        collector=collector,
        weights=ProviderPerformanceWeights(min_samples_for_full_confidence=5),
    )


@pytest.fixture
def routing_registry() -> ProviderRegistry:
    env = {"TITAN_BRAVE_SEARCH_API_KEY": "test-brave-key-for-performance-tests"}
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


def test_high_latency_lowers_performance_score(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1201: High average latency reduces composite performance score."""
    _seed_collector(collector, "brave_search", count=6, duration_ms=30.0)
    fast_score = performance_model.get_metrics("brave_search").performance_score
    collector.clear()
    performance_model.invalidate()
    _seed_collector(collector, "brave_search", count=6, duration_ms=4500.0)
    metrics = performance_model.get_metrics("brave_search")
    assert metrics.sample_count == 6
    assert metrics.average_latency_ms == pytest.approx(4500.0)
    assert metrics.performance_score < fast_score


def test_excellent_provider_high_score(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1201: Fast, reliable provider earns high performance score."""
    _seed_collector(collector, "brave_search", count=8, duration_ms=20.0)
    metrics = performance_model.get_metrics("brave_search")
    assert metrics.success_rate == pytest.approx(1.0)
    assert metrics.performance_score > 80.0
    assert metrics.historical_confidence == pytest.approx(1.0)


def test_provider_degradation_detected(
    collector: ProviderTelemetryCollector,
) -> None:
    """P10B-1201: Failures and retries degrade performance score."""
    model = ProviderPerformanceModel(
        collector=collector,
        weights=ProviderPerformanceWeights(
            min_samples_for_full_confidence=5,
            degraded_threshold=55.0,
        ),
    )
    for _ in range(8):
        collector.record(
            _record("web_search", success=False, duration_ms=200.0, retry_count=2),
        )
    metrics = model.get_metrics("web_search")
    assert metrics.failure_rate == pytest.approx(1.0)
    assert metrics.retry_rate > 0.0
    assert metrics.performance_score < model.weights.degraded_threshold
    assert model.is_historically_degraded("web_search")


def test_historical_recovery_improves_score(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1201: Recent successes recover performance after failures."""
    for _ in range(3):
        collector.record(_record("brave_search", success=False, duration_ms=500.0))
    degraded = performance_model.get_metrics("brave_search").performance_score
    _seed_collector(collector, "brave_search", count=10, duration_ms=25.0)
    performance_model.invalidate("brave_search")
    recovered = performance_model.get_metrics("brave_search").performance_score
    assert recovered > degraded
    assert not performance_model.is_historically_degraded("brave_search")


def test_multiple_providers_ranked_by_history(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
    routing_registry: ProviderRegistry,
) -> None:
    """P10B-1202: Historical performance influences provider ranking order."""
    _seed_collector(collector, "brave_search", count=6, duration_ms=30.0)
    _seed_collector(
        collector,
        "web_search",
        count=6,
        success=False,
        duration_ms=800.0,
        retry_count=1,
    )
    ranker = ProviderRanker(performance_model=performance_model)
    classification = IntentClassification(
        intent=Intent.WEB_SEARCH,
        confidence=0.85,
        reason="test",
    )
    ranked = ranker.rank(
        "Latest Nvidia news",
        classification,
        selected_tool="web_search",
        provider_registry=routing_registry,
    )
    assert len(ranked) >= 2
    brave = next(c for c in ranked if c.provider_id == "brave_search")
    stub = next(c for c in ranked if c.provider_id == "web_search")
    assert brave.score > stub.score
    assert "historical perf" in brave.reason


def test_equal_providers_neutral_adjustment(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1202: Equal telemetry yields neutral ranking adjustment."""
    _seed_collector(collector, "provider_a", count=5, duration_ms=100.0)
    _seed_collector(collector, "provider_b", count=5, duration_ms=100.0)
    delta_a, _ = performance_model.ranking_adjustment("provider_a")
    delta_b, _ = performance_model.ranking_adjustment("provider_b")
    assert delta_a == pytest.approx(delta_b, abs=0.01)


def test_performance_snapshot_export(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1204: ProviderPerformanceSnapshot exposes provider metrics."""
    _seed_collector(collector, "brave_search", count=3)
    snapshot = performance_model.snapshot()
    assert snapshot.generated_at
    assert len(snapshot.providers) == 1
    data = snapshot.to_dict()
    assert data["providers"][0]["provider_id"] == "brave_search"
    assert "performance_score" in data["providers"][0]


def test_fallback_policy_uses_performance_model(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
) -> None:
    """P10B-1203: Degraded telemetry prefers fallback over retry."""
    for _ in range(6):
        collector.record(_record("web_search", success=False, retry_count=2))
    policy = ProviderFallbackPolicy(
        config=ProviderFallbackPolicyConfig(allow_provider_fallback=True),
        performance_model=performance_model,
    )
    outcome = policy.evaluate(
        FallbackEvaluationContext(
            provider_id="web_search",
            capability="web_search",
            execution_mode=ExecutionMode.MOCK,
            provider_health=ToolHealthState.DEGRADED,
        ),
    )
    assert outcome.decision == FallbackDecision.ALLOW_FALLBACK
    assert "historically degraded" in outcome.reason


def test_decision_report_performance_fields(
    collector: ProviderTelemetryCollector,
    performance_model: ProviderPerformanceModel,
    routing_registry: ProviderRegistry,
) -> None:
    """P10B-1205: DecisionReport includes performance_score and confidence."""
    _seed_collector(collector, "brave_search", count=6, duration_ms=35.0)
    from tools.capability_catalog import CapabilityCatalog
    from tools.tool_capability import ToolCapability
    from tools.tool_enums import InvocationMode, RiskLevel

    catalog = CapabilityCatalog()
    catalog.register(
        ToolCapability.from_schema(
            "web_search",
            "Test web_search",
            [],
            invocation_mode=InvocationMode.SYNC,
            execution_mode=ExecutionMode.LIVE,
            risk_level=RiskLevel.LOW,
            provider_name="web_search",
        ),
    )
    resolver = CapabilityAvailabilityResolver(
        catalog=catalog,
        provider_registry=routing_registry,
        health_monitor=HealthMonitor(),
    )
    engine = ToolDecisionEngine(performance_model=performance_model)
    report = engine.decide("Latest Nvidia news", availability_resolver=resolver)
    assert report.selected_provider
    assert report.performance_score is not None
    assert report.performance_score > 0.0
    assert report.ranking_reason
    assert report.historical_confidence is not None
    data = report.to_dict()
    assert data["performance_score"] is not None
    assert data["ranking_reason"]
    assert data["historical_confidence"] is not None
    restored = ToolDecisionReport.from_dict(data)
    assert restored.performance_score == report.performance_score


def test_configurable_performance_weights(
    collector: ProviderTelemetryCollector,
) -> None:
    """P10B-1206: Performance weighting is configurable."""
    _seed_collector(collector, "slow_provider", count=6, duration_ms=4000.0)
    latency_heavy = ProviderPerformanceModel(
        collector=collector,
        weights=ProviderPerformanceWeights(
            latency_weight=0.90,
            failure_weight=0.02,
            retry_weight=0.02,
            health_weight=0.02,
            success_weight=0.04,
            min_samples_for_full_confidence=5,
        ),
    )
    balanced = ProviderPerformanceModel(
        collector=collector,
        weights=ProviderPerformanceWeights(min_samples_for_full_confidence=5),
    )
    latency_score = latency_heavy.get_metrics("slow_provider").performance_score
    balanced_score = balanced.get_metrics("slow_provider").performance_score
    assert latency_score < balanced_score


def test_legacy_compatibility_without_performance_model(
    routing_registry: ProviderRegistry,
) -> None:
    """Legacy path without performance model preserves prior ranking behavior."""
    ranker = ProviderRanker()
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
    assert ranked[0].provider_id == "brave_search"
    engine = ToolDecisionEngine()
    report = engine.decide("Latest Nvidia news")
    assert report.performance_score is None
    assert report.historical_confidence is None
    assert report.ranking_reason == ""


def test_legacy_fallback_policy_without_performance_model() -> None:
    """P10B-1203: Fallback policy without performance model keeps Batch 9 behavior."""
    policy = ProviderFallbackPolicy(
        config=ProviderFallbackPolicyConfig(allow_retry=True),
    )
    outcome = policy.evaluate(
        FallbackEvaluationContext(
            provider_id="web_search",
            capability="web_search",
            execution_mode=ExecutionMode.MOCK,
            provider_health=ToolHealthState.DEGRADED,
        ),
    )
    assert outcome.decision == FallbackDecision.RETRY_ORIGINAL

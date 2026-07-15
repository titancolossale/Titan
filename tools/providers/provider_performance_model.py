# =====================================
# Titan Provider Performance Model
# =====================================

"""Telemetry-driven provider performance scoring for ranking and fallback (P10B-1201–P10B-1206)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from config.settings import (
    TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD,
    TITAN_PROVIDER_PERF_FAILURE_WEIGHT,
    TITAN_PROVIDER_PERF_HEALTH_WEIGHT,
    TITAN_PROVIDER_PERF_LATENCY_WEIGHT,
    TITAN_PROVIDER_PERF_MAX_LATENCY_MS,
    TITAN_PROVIDER_PERF_MIN_SAMPLES,
    TITAN_PROVIDER_PERF_RETRY_WEIGHT,
    TITAN_PROVIDER_PERF_SUCCESS_WEIGHT,
)
from tools.providers.provider_telemetry import (
    ProviderTelemetryCollector,
    ProviderUsageStats,
)

_NEUTRAL_SCORE = 50.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ProviderPerformanceWeights:
    """Configurable performance weighting (P10B-1206)."""

    latency_weight: float = TITAN_PROVIDER_PERF_LATENCY_WEIGHT
    failure_weight: float = TITAN_PROVIDER_PERF_FAILURE_WEIGHT
    retry_weight: float = TITAN_PROVIDER_PERF_RETRY_WEIGHT
    health_weight: float = TITAN_PROVIDER_PERF_HEALTH_WEIGHT
    success_weight: float = TITAN_PROVIDER_PERF_SUCCESS_WEIGHT
    max_latency_ms: float = TITAN_PROVIDER_PERF_MAX_LATENCY_MS
    min_samples_for_full_confidence: int = TITAN_PROVIDER_PERF_MIN_SAMPLES
    degraded_threshold: float = TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD

    @property
    def total_weight(self) -> float:
        """Sum of component weights for normalization."""
        return (
            self.latency_weight
            + self.failure_weight
            + self.retry_weight
            + self.health_weight
            + self.success_weight
        )


@dataclass(frozen=True)
class ProviderPerformanceMetrics:
    """Rolling performance metrics for a single provider."""

    provider_id: str
    average_latency_ms: float
    success_rate: float
    retry_rate: float
    failure_rate: float
    health_stability: float
    sample_count: int
    performance_score: float
    ranking_reason: str
    historical_confidence: float

    def to_dict(self) -> dict:
        """Serialize for snapshots and DecisionReport export."""
        return {
            "provider_id": self.provider_id,
            "average_latency_ms": round(self.average_latency_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "retry_rate": round(self.retry_rate, 4),
            "failure_rate": round(self.failure_rate, 4),
            "health_stability": round(self.health_stability, 4),
            "sample_count": self.sample_count,
            "performance_score": round(self.performance_score, 2),
            "ranking_reason": self.ranking_reason,
            "historical_confidence": round(self.historical_confidence, 4),
        }


@dataclass(frozen=True)
class ProviderPerformanceSnapshot:
    """Point-in-time provider performance aggregate (P10B-1204)."""

    generated_at: str
    providers: tuple[ProviderPerformanceMetrics, ...]

    def to_dict(self) -> dict:
        """Serialize the performance snapshot."""
        return {
            "generated_at": self.generated_at,
            "providers": [item.to_dict() for item in self.providers],
        }


@dataclass
class ProviderPerformanceModel:
    """Compute rolling provider performance scores from persisted telemetry (P10B-1201)."""

    collector: ProviderTelemetryCollector
    weights: ProviderPerformanceWeights = field(default_factory=ProviderPerformanceWeights)
    _cache: dict[str, ProviderPerformanceMetrics] = field(default_factory=dict, init=False)

    def get_metrics(self, provider_id: str) -> ProviderPerformanceMetrics:
        """Return cached or freshly computed metrics for a provider."""
        if provider_id not in self._cache:
            self._cache[provider_id] = self._compute_metrics(provider_id)
        return self._cache[provider_id]

    def invalidate(self, provider_id: str | None = None) -> None:
        """Clear cached metrics after telemetry updates."""
        if provider_id is None:
            self._cache.clear()
            return
        self._cache.pop(provider_id, None)

    def snapshot(self) -> ProviderPerformanceSnapshot:
        """Export performance metrics for all providers with telemetry (P10B-1204)."""
        provider_ids = sorted(self.collector.snapshot().provider_stats, key=lambda s: s.provider_id)
        metrics = tuple(
            self.get_metrics(stats.provider_id)
            for stats in provider_ids
            if stats.usage_count > 0
        )
        return ProviderPerformanceSnapshot(
            generated_at=_utc_now_iso(),
            providers=metrics,
        )

    def ranking_adjustment(self, provider_id: str) -> tuple[float, str]:
        """Return score delta and reason fragment for ProviderRanker integration."""
        metrics = self.get_metrics(provider_id)
        if metrics.sample_count == 0:
            return 0.0, ""
        delta = (
            (metrics.performance_score - _NEUTRAL_SCORE)
            / _NEUTRAL_SCORE
            * 15.0
            * metrics.historical_confidence
        )
        reason = (
            f"historical perf={metrics.performance_score:.0f} "
            f"(conf={metrics.historical_confidence:.2f})"
        )
        return round(delta, 2), reason

    def is_historically_degraded(self, provider_id: str) -> bool:
        """Return True when telemetry indicates sustained poor performance."""
        metrics = self.get_metrics(provider_id)
        if metrics.sample_count == 0:
            return False
        return (
            metrics.historical_confidence >= 0.3
            and metrics.performance_score < self.weights.degraded_threshold
        )

    def _compute_metrics(self, provider_id: str) -> ProviderPerformanceMetrics:
        stats = self.collector.get_provider_stats(provider_id)
        sample_count = stats.usage_count
        if sample_count == 0:
            return self._neutral_metrics(provider_id)

        success_rate = stats.success_rate
        failure_rate = stats.failure_count / sample_count
        retry_rate = stats.retry_count / sample_count
        average_latency = stats.average_latency_ms
        health_stability = self._health_stability(provider_id)

        latency_score = self._latency_component(average_latency)
        success_score = success_rate * 100.0
        failure_score = max(0.0, 100.0 - failure_rate * 100.0)
        retry_score = max(0.0, 100.0 - min(retry_rate * 100.0, 100.0))
        health_score = health_stability * 100.0

        total_weight = self.weights.total_weight or 1.0
        performance_score = (
            latency_score * self.weights.latency_weight
            + success_score * self.weights.success_weight
            + failure_score * self.weights.failure_weight
            + retry_score * self.weights.retry_weight
            + health_score * self.weights.health_weight
        ) / total_weight

        historical_confidence = min(
            1.0,
            sample_count / max(self.weights.min_samples_for_full_confidence, 1),
        )
        ranking_reason = self._build_ranking_reason(
            provider_id=provider_id,
            performance_score=performance_score,
            average_latency_ms=average_latency,
            success_rate=success_rate,
            failure_rate=failure_rate,
            retry_rate=retry_rate,
            health_stability=health_stability,
            historical_confidence=historical_confidence,
        )
        return ProviderPerformanceMetrics(
            provider_id=provider_id,
            average_latency_ms=average_latency,
            success_rate=success_rate,
            retry_rate=retry_rate,
            failure_rate=failure_rate,
            health_stability=health_stability,
            sample_count=sample_count,
            performance_score=round(performance_score, 2),
            ranking_reason=ranking_reason,
            historical_confidence=round(historical_confidence, 4),
        )

    def _neutral_metrics(self, provider_id: str) -> ProviderPerformanceMetrics:
        return ProviderPerformanceMetrics(
            provider_id=provider_id,
            average_latency_ms=0.0,
            success_rate=0.0,
            retry_rate=0.0,
            failure_rate=0.0,
            health_stability=1.0,
            sample_count=0,
            performance_score=_NEUTRAL_SCORE,
            ranking_reason="No historical telemetry; neutral performance assumed.",
            historical_confidence=0.0,
        )

    def _latency_component(self, average_latency_ms: float) -> float:
        if average_latency_ms <= 0:
            return _NEUTRAL_SCORE
        max_latency_ms = max(self.weights.max_latency_ms, 1.0)
        ratio = min(average_latency_ms / max_latency_ms, 1.0)
        return max(0.0, 100.0 - ratio * 100.0)

    def _health_stability(self, provider_id: str) -> float:
        transitions = [
            item
            for item in self.collector.snapshot().health_transitions
            if item.provider_id == provider_id
        ]
        if not transitions:
            return 1.0
        penalty = min(len(transitions) * 0.15, 0.9)
        return max(0.1, 1.0 - penalty)

    @staticmethod
    def _build_ranking_reason(
        *,
        provider_id: str,
        performance_score: float,
        average_latency_ms: float,
        success_rate: float,
        failure_rate: float,
        retry_rate: float,
        health_stability: float,
        historical_confidence: float,
    ) -> str:
        return (
            f"{provider_id}: score={performance_score:.0f} "
            f"(latency={average_latency_ms:.0f}ms, success={success_rate:.0%}, "
            f"failures={failure_rate:.0%}, retries={retry_rate:.2f}/call, "
            f"health_stability={health_stability:.2f}, "
            f"confidence={historical_confidence:.2f})"
        )

# =====================================
# Titan Provider Dashboard Model
# =====================================

"""Serializable provider execution inspection model for future dashboards (P10B-206, P10B-1006)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.providers.provider_metadata import ProviderMetadata
from tools.providers.provider_performance_model import ProviderPerformanceSnapshot
from tools.providers.provider_telemetry import (
    ProviderTelemetryCollector,
    ProviderTelemetrySnapshot,
)


@dataclass
class ProviderDashboardSnapshot:
    """Dashboard-ready snapshot of provider registry state and recent executions."""

    providers: list[dict] = field(default_factory=list)
    recent_executions: list[dict] = field(default_factory=list)
    generated_at: str = ""
    telemetry_summary: dict = field(default_factory=dict)
    telemetry_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize the full dashboard snapshot."""
        return {
            "generated_at": self.generated_at,
            "providers": self.providers,
            "recent_executions": self.recent_executions,
            "telemetry_summary": self.telemetry_summary,
            "telemetry_metadata": self.telemetry_metadata,
        }

    @classmethod
    def build(
        cls,
        provider_metadata: list[ProviderMetadata],
        telemetry: ProviderTelemetryCollector | None = None,
        *,
        generated_at: str = "",
    ) -> ProviderDashboardSnapshot:
        """Build a snapshot from registry metadata and optional telemetry."""
        from tools.providers.provider_telemetry import _utc_now_iso

        ts = generated_at or _utc_now_iso()
        executions: list[dict] = []
        telemetry_summary: dict = {}
        telemetry_metadata: dict = {}
        if telemetry is not None:
            executions = telemetry.export()
            snapshot = telemetry.snapshot()
            telemetry_summary = {
                "total_executions": snapshot.total_executions,
                "total_fallbacks": snapshot.total_fallbacks,
                "total_retries": snapshot.total_retries,
                "total_failures": snapshot.total_failures,
                "provider_stats": [stats.to_dict() for stats in snapshot.provider_stats],
            }
            telemetry_metadata = build_dashboard_telemetry_metadata(snapshot)
        return cls(
            providers=[meta.to_dict() for meta in provider_metadata],
            recent_executions=executions,
            generated_at=ts,
            telemetry_summary=telemetry_summary,
            telemetry_metadata=telemetry_metadata,
        )


def build_dashboard_telemetry_metadata(snapshot: ProviderTelemetrySnapshot) -> dict:
    """Export visualization-ready telemetry metadata without UI (P10B-1006)."""
    return {
        "schema": "titan.provider_telemetry.v1",
        "generated_at": snapshot.generated_at,
        "metrics": {
            "executions": snapshot.total_executions,
            "fallbacks": snapshot.total_fallbacks,
            "retries": snapshot.total_retries,
            "failures": snapshot.total_failures,
        },
        "providers": [
            {
                "id": stats.provider_id,
                "usage": stats.usage_count,
                "success_rate": stats.success_rate,
                "avg_latency_ms": stats.average_latency_ms,
                "fallbacks": stats.fallback_count,
            }
            for stats in snapshot.provider_stats
        ],
        "health_transitions": [item.to_dict() for item in snapshot.health_transitions],
        "chart_hints": {
            "latency_series": "recent_records.latency_ms",
            "success_rate_gauge": "providers.success_rate",
            "fallback_counter": "metrics.fallbacks",
            "health_timeline": "health_transitions",
        },
    }


def build_dashboard_snapshot(
    provider_metadata: list[ProviderMetadata],
    telemetry: ProviderTelemetryCollector | None = None,
) -> dict:
    """Convenience export for dashboard consumers."""
    return ProviderDashboardSnapshot.build(provider_metadata, telemetry).to_dict()


def build_performance_dashboard_metadata(
    snapshot: ProviderPerformanceSnapshot | None,
) -> dict:
    """Export visualization-ready performance metadata without UI (P10B-1306)."""
    if snapshot is None:
        return {
            "schema": "titan.provider_performance.v1",
            "generated_at": "",
            "providers": [],
            "chart_hints": {
                "performance_score_gauge": "providers.performance_score",
                "latency_gauge": "providers.average_latency_ms",
                "success_rate_gauge": "providers.success_rate",
                "confidence_indicator": "providers.historical_confidence",
                "degraded_threshold": "settings.TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD",
            },
            "query_apis": [
                "export_provider_performance_snapshot",
                "export_provider_performance_analytics_metadata",
            ],
        }
    return {
        "schema": "titan.provider_performance.v1",
        "generated_at": snapshot.generated_at,
        "providers": [
            {
                "id": item.provider_id,
                "performance_score": item.performance_score,
                "average_latency_ms": item.average_latency_ms,
                "success_rate": item.success_rate,
                "failure_rate": item.failure_rate,
                "retry_rate": item.retry_rate,
                "sample_count": item.sample_count,
                "historical_confidence": item.historical_confidence,
            }
            for item in snapshot.providers
        ],
        "chart_hints": {
            "performance_score_gauge": "providers.performance_score",
            "latency_gauge": "providers.average_latency_ms",
            "success_rate_gauge": "providers.success_rate",
            "confidence_indicator": "providers.historical_confidence",
            "degraded_threshold": "settings.TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD",
        },
        "query_apis": [
            "export_provider_performance_snapshot",
            "export_provider_performance_analytics_metadata",
        ],
    }

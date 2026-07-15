# =====================================
# Titan Provider Telemetry
# =====================================

"""Provider execution telemetry for audit and dashboard inspection (P10B-203, P10B-1002)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ProviderHealthTransition:
    """Record of a provider health state change for telemetry aggregation."""

    provider_id: str
    from_state: str
    to_state: str
    timestamp: str = field(default_factory=_utc_now_iso)
    reason: str = ""

    def to_dict(self) -> dict:
        """Serialize for dashboard export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProviderHealthTransition:
        """Restore a health transition from persisted JSON."""
        return cls(
            provider_id=str(data.get("provider_id", "")),
            from_state=str(data.get("from_state", "")),
            to_state=str(data.get("to_state", "")),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
            reason=str(data.get("reason", "")),
        )


@dataclass
class ProviderUsageStats:
    """Aggregated execution statistics for a single provider."""

    provider_id: str
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    fallback_count: int = 0
    retry_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Return success ratio in [0.0, 1.0]."""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    @property
    def average_latency_ms(self) -> float:
        """Return mean latency across recorded executions."""
        if self.usage_count == 0:
            return 0.0
        return self.total_latency_ms / self.usage_count

    def to_dict(self) -> dict:
        """Serialize for dashboard and snapshot export."""
        return {
            "provider_id": self.provider_id,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "fallback_count": self.fallback_count,
            "retry_count": self.retry_count,
            "total_latency_ms": self.total_latency_ms,
            "success_rate": round(self.success_rate, 4),
            "average_latency_ms": round(self.average_latency_ms, 2),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProviderUsageStats:
        """Restore provider usage stats from persisted JSON."""
        return cls(
            provider_id=str(data.get("provider_id", "")),
            usage_count=int(data.get("usage_count", 0)),
            success_count=int(data.get("success_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            fallback_count=int(data.get("fallback_count", 0)),
            retry_count=int(data.get("retry_count", 0)),
            total_latency_ms=float(data.get("total_latency_ms", 0.0)),
        )


@dataclass(frozen=True)
class ProviderExecutionRecord:
    """Single provider execution telemetry record."""

    provider_selected: str
    duration_ms: float
    provider_health: str
    provider_version: str
    success: bool
    retry_count: int
    decision_id: str
    runtime_id: str
    execution_path: tuple[str, ...] = ()
    tool_name: str = ""
    action: str = ""
    error: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    execution_mode: str = ""
    record_index: int = 0
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict:
        """Serialize for JSON export and dashboard models."""
        data = asdict(self)
        data["execution_path"] = list(self.execution_path)
        data["latency_ms"] = self.duration_ms
        return data

    @classmethod
    def from_dict(cls, data: dict) -> ProviderExecutionRecord:
        """Restore a record from persisted JSON."""
        path = data.get("execution_path") or []
        return cls(
            provider_selected=str(data.get("provider_selected", "")),
            duration_ms=float(data.get("duration_ms", data.get("latency_ms", 0.0))),
            provider_health=str(data.get("provider_health", "")),
            provider_version=str(data.get("provider_version", "")),
            success=bool(data.get("success", False)),
            retry_count=int(data.get("retry_count", 0)),
            decision_id=str(data.get("decision_id", "")),
            runtime_id=str(data.get("runtime_id", "")),
            execution_path=tuple(path) if isinstance(path, list) else (),
            tool_name=str(data.get("tool_name", "")),
            action=str(data.get("action", "")),
            error=str(data.get("error", "")),
            fallback_used=bool(data.get("fallback_used", False)),
            fallback_reason=str(data.get("fallback_reason", "")),
            execution_mode=str(data.get("execution_mode", "")),
            record_index=int(data.get("record_index", 0)),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
        )


@dataclass(frozen=True)
class ProviderTelemetrySnapshot:
    """Point-in-time telemetry aggregate for inspection APIs (P10B-1003)."""

    generated_at: str
    total_executions: int
    total_fallbacks: int
    total_retries: int
    total_failures: int
    provider_stats: tuple[ProviderUsageStats, ...]
    health_transitions: tuple[ProviderHealthTransition, ...]
    recent_records: tuple[ProviderExecutionRecord, ...]

    def to_dict(self) -> dict:
        """Serialize the full telemetry snapshot."""
        return {
            "generated_at": self.generated_at,
            "total_executions": self.total_executions,
            "total_fallbacks": self.total_fallbacks,
            "total_retries": self.total_retries,
            "total_failures": self.total_failures,
            "provider_stats": [stats.to_dict() for stats in self.provider_stats],
            "health_transitions": [item.to_dict() for item in self.health_transitions],
            "recent_records": [record.to_dict() for record in self.recent_records],
        }


@dataclass
class ProviderTelemetryCollector:
    """In-memory collector for provider execution telemetry and aggregates."""

    _records: list[ProviderExecutionRecord] = field(default_factory=list)
    _provider_stats: dict[str, ProviderUsageStats] = field(default_factory=dict)
    _health_transitions: list[ProviderHealthTransition] = field(default_factory=list)
    _last_health: dict[str, str] = field(default_factory=dict)
    _total_fallbacks: int = 0
    _total_retries: int = 0
    _total_failures: int = 0

    def record(self, entry: ProviderExecutionRecord) -> ProviderExecutionRecord:
        """Append a provider execution record and update aggregates."""
        indexed = ProviderExecutionRecord(
            provider_selected=entry.provider_selected,
            duration_ms=entry.duration_ms,
            provider_health=entry.provider_health,
            provider_version=entry.provider_version,
            success=entry.success,
            retry_count=entry.retry_count,
            decision_id=entry.decision_id,
            runtime_id=entry.runtime_id,
            execution_path=entry.execution_path,
            tool_name=entry.tool_name,
            action=entry.action,
            error=entry.error,
            fallback_used=entry.fallback_used,
            fallback_reason=entry.fallback_reason,
            execution_mode=entry.execution_mode,
            record_index=len(self._records),
            timestamp=entry.timestamp,
        )
        self._records.append(indexed)
        self._update_stats(indexed)
        return indexed

    def record_health_transition(
        self,
        provider_id: str,
        from_state: str,
        to_state: str,
        *,
        reason: str = "",
    ) -> None:
        """Track a provider health state transition."""
        if from_state == to_state:
            return
        transition = ProviderHealthTransition(
            provider_id=provider_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        )
        self._health_transitions.append(transition)
        self._last_health[provider_id] = to_state

    def observe_health(self, provider_id: str, state: str) -> None:
        """Record transition when health differs from last observed state."""
        previous = self._last_health.get(provider_id)
        if previous is None:
            self._last_health[provider_id] = state
            return
        if previous != state:
            self.record_health_transition(provider_id, previous, state)

    def list_records(self) -> list[ProviderExecutionRecord]:
        """Return all collected records."""
        return list(self._records)

    def get_provider_stats(self, provider_id: str) -> ProviderUsageStats:
        """Return aggregated stats for a provider (empty stats when unknown)."""
        return self._provider_stats.get(
            provider_id,
            ProviderUsageStats(provider_id=provider_id),
        )

    def snapshot(self, *, recent_limit: int = 50) -> ProviderTelemetrySnapshot:
        """Export a point-in-time telemetry snapshot (P10B-1003)."""
        recent = self._records[-recent_limit:] if recent_limit > 0 else []
        return ProviderTelemetrySnapshot(
            generated_at=_utc_now_iso(),
            total_executions=len(self._records),
            total_fallbacks=self._total_fallbacks,
            total_retries=self._total_retries,
            total_failures=self._total_failures,
            provider_stats=tuple(
                sorted(self._provider_stats.values(), key=lambda s: s.provider_id),
            ),
            health_transitions=tuple(self._health_transitions),
            recent_records=tuple(recent),
        )

    def export(self) -> list[dict]:
        """Export all records as serializable dicts."""
        return [record.to_dict() for record in self._records]

    def clear(self) -> None:
        """Clear collected records and aggregates (primarily for tests)."""
        self._records.clear()
        self._provider_stats.clear()
        self._health_transitions.clear()
        self._last_health.clear()
        self._total_fallbacks = 0
        self._total_retries = 0
        self._total_failures = 0

    def restore_from_persisted(self, payload: dict) -> None:
        """Restore collector state from a persisted telemetry snapshot (P10B-1103)."""
        self.clear()
        for item in payload.get("records") or []:
            if isinstance(item, dict):
                self._records.append(ProviderExecutionRecord.from_dict(item))
        for item in payload.get("health_transitions") or []:
            if isinstance(item, dict):
                transition = ProviderHealthTransition.from_dict(item)
                self._health_transitions.append(transition)
                self._last_health[transition.provider_id] = transition.to_state
        for provider_id, stats_data in (payload.get("provider_stats") or {}).items():
            if isinstance(stats_data, dict):
                self._provider_stats[str(provider_id)] = ProviderUsageStats.from_dict(stats_data)
        aggregates = payload.get("aggregates") or {}
        self._total_fallbacks = int(aggregates.get("total_fallbacks", 0))
        self._total_retries = int(aggregates.get("total_retries", 0))
        self._total_failures = int(aggregates.get("total_failures", 0))

    def export_persisted_payload(self) -> dict:
        """Export full collector state for JSON persistence (P10B-1101)."""
        return {
            "records": [record.to_dict() for record in self._records],
            "health_transitions": [item.to_dict() for item in self._health_transitions],
            "provider_stats": {
                provider_id: stats.to_dict()
                for provider_id, stats in self._provider_stats.items()
            },
            "aggregates": {
                "total_fallbacks": self._total_fallbacks,
                "total_retries": self._total_retries,
                "total_failures": self._total_failures,
            },
        }

    def _update_stats(self, record: ProviderExecutionRecord) -> None:
        stats = self._provider_stats.setdefault(
            record.provider_selected,
            ProviderUsageStats(provider_id=record.provider_selected),
        )
        stats.usage_count += 1
        stats.total_latency_ms += record.duration_ms
        stats.retry_count += record.retry_count
        self._total_retries += record.retry_count
        if record.success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
            self._total_failures += 1
        if record.fallback_used:
            stats.fallback_count += 1
            self._total_fallbacks += 1

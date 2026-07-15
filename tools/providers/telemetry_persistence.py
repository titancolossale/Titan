# =====================================
# Titan Telemetry Persistence
# =====================================

"""Persist provider telemetry across sessions with retention and historical queries (P10B-1101–P10B-1106)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from config.settings import (
    TITAN_TELEMETRY_MAX_RECORDS,
    TITAN_TELEMETRY_RETENTION,
    TOOL_TELEMETRY_PATH,
)
from tools.providers.provider_telemetry import (
    ProviderExecutionRecord,
    ProviderTelemetryCollector,
)
from tools.tool_run_store import ToolRunStore, tool_run_to_dict

SCHEMA_VERSION = 1


class TelemetryRetentionPolicy(str, Enum):
    """Configurable telemetry retention windows (P10B-1102)."""

    HOURS_24 = "24h"
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    UNLIMITED = "unlimited"


_RETENTION_SECONDS: dict[TelemetryRetentionPolicy, int | None] = {
    TelemetryRetentionPolicy.HOURS_24: 86400,
    TelemetryRetentionPolicy.DAYS_7: 7 * 86400,
    TelemetryRetentionPolicy.DAYS_30: 30 * 86400,
    TelemetryRetentionPolicy.UNLIMITED: None,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def parse_retention_policy(value: str) -> TelemetryRetentionPolicy:
    """Parse retention policy from configuration string."""
    normalized = value.strip().lower()
    for policy in TelemetryRetentionPolicy:
        if policy.value == normalized:
            return policy
    return TelemetryRetentionPolicy.DAYS_7


def _parse_timestamp(value: str) -> datetime | None:
    """Parse ISO-8601 timestamp; return None when invalid."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def default_schema(*, retention_policy: str = TelemetryRetentionPolicy.DAYS_7.value) -> dict[str, Any]:
    """Return empty telemetry persistence document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "retention_policy": retention_policy,
        "saved_at": _utc_now_iso(),
        "records": [],
        "health_transitions": [],
        "provider_stats": {},
        "aggregates": {
            "total_fallbacks": 0,
            "total_retries": 0,
            "total_failures": 0,
        },
    }


def _record_within_retention(record: ProviderExecutionRecord, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    timestamp = _parse_timestamp(record.timestamp)
    if timestamp is None:
        return True
    return timestamp >= cutoff


@dataclass
class TelemetryPersistenceManager:
    """Save, load, rotate, and query persisted provider telemetry (P10B-1101)."""

    file_path: Path = field(default_factory=lambda: TOOL_TELEMETRY_PATH)
    retention_policy: TelemetryRetentionPolicy = field(
        default_factory=lambda: parse_retention_policy(TITAN_TELEMETRY_RETENTION),
    )
    persist: bool = False
    max_records: int = TITAN_TELEMETRY_MAX_RECORDS

    def save_snapshot(self, collector: ProviderTelemetryCollector) -> None:
        """Persist current collector state to disk."""
        if not self.persist:
            return
        self.compact_old_records(collector)
        if len(collector.list_records()) > self.max_records:
            self.rotate_history()
        payload = default_schema(retention_policy=self.retention_policy.value)
        payload.update(collector.export_persisted_payload())
        payload["saved_at"] = _utc_now_iso()
        payload["retention_policy"] = self.retention_policy.value
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

    def load_snapshot(self, collector: ProviderTelemetryCollector) -> bool:
        """Load persisted telemetry into the collector; return True when data was restored."""
        raw = self._read_document()
        if not raw.get("records") and not raw.get("health_transitions"):
            return False
        collector.restore_from_persisted(raw)
        removed = self.compact_old_records(collector)
        if removed:
            self.save_snapshot(collector)
        return True

    def reload_on_startup(self, collector: ProviderTelemetryCollector) -> bool:
        """Restore telemetry from disk on startup (P10B-1103)."""
        if not self.persist:
            return False
        return self.load_snapshot(collector)

    def rotate_history(self) -> Path | None:
        """Archive the current telemetry file before overwriting (P10B-1101)."""
        if not self.file_path.exists():
            return None
        archive_dir = self.file_path.parent / "telemetry_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        archive_path = archive_dir / f"{self.file_path.stem}.{stamp}.json"
        shutil.copy2(self.file_path, archive_path)
        return archive_path

    def compact_old_records(self, collector: ProviderTelemetryCollector) -> int:
        """Drop records and transitions older than the retention policy."""
        cutoff = self._retention_cutoff()
        if cutoff is None:
            return 0

        original_records = collector.list_records()
        kept_records = [
            record
            for record in original_records
            if _record_within_retention(record, cutoff)
        ]
        removed = len(original_records) - len(kept_records)
        if removed == 0:
            return 0

        kept_transitions = [
            transition
            for transition in collector.snapshot().health_transitions
            if (
                _parse_timestamp(transition.timestamp) is None
                or _parse_timestamp(transition.timestamp) >= cutoff
            )
        ]

        collector.clear()
        for record in kept_records:
            collector.record(record)
        for transition in kept_transitions:
            collector._health_transitions.append(transition)
            collector._last_health[transition.provider_id] = transition.to_state
        return removed

    def records_for_run(
        self,
        run_id: str,
        collector: ProviderTelemetryCollector,
    ) -> list[ProviderExecutionRecord]:
        """Return telemetry records correlated with a tool run id (P10B-1104)."""
        return [
            record
            for record in collector.list_records()
            if record.runtime_id == run_id
        ]

    def correlate_with_run_store(
        self,
        run_id: str,
        collector: ProviderTelemetryCollector,
        run_store: ToolRunStore,
    ) -> dict[str, Any]:
        """Combine telemetry and ToolRunStore data for drill-down (P10B-1104)."""
        run = run_store.get(run_id)
        records = self.records_for_run(run_id, collector)
        return {
            "run_id": run_id,
            "correlation_key": "runtime_id",
            "tool_run": tool_run_to_dict(run) if run is not None else None,
            "telemetry_records": [record.to_dict() for record in records],
            "record_count": len(records),
        }

    def last_hour(self, collector: ProviderTelemetryCollector) -> dict[str, Any]:
        """Return telemetry from the last hour (P10B-1105)."""
        return self._historical_window(collector, hours=1)

    def last_day(self, collector: ProviderTelemetryCollector) -> dict[str, Any]:
        """Return telemetry from the last 24 hours (P10B-1105)."""
        return self._historical_window(collector, hours=24)

    def provider_history(
        self,
        provider_id: str,
        collector: ProviderTelemetryCollector,
        *,
        hours: int | None = None,
    ) -> dict[str, Any]:
        """Return execution history for a provider (P10B-1105)."""
        cutoff = _utc_now() - timedelta(hours=hours) if hours is not None else None
        records = [
            record
            for record in collector.list_records()
            if record.provider_selected == provider_id
            and _record_within_retention(record, cutoff)
        ]
        stats = collector.get_provider_stats(provider_id)
        return {
            "provider_id": provider_id,
            "window_hours": hours,
            "record_count": len(records),
            "records": [record.to_dict() for record in records],
            "aggregated_stats": stats.to_dict(),
        }

    def latency_history(
        self,
        collector: ProviderTelemetryCollector,
        *,
        provider_id: str | None = None,
        hours: int | None = None,
    ) -> dict[str, Any]:
        """Return latency time-series metadata for analytics (P10B-1105)."""
        cutoff = _utc_now() - timedelta(hours=hours) if hours is not None else None
        points: list[dict[str, Any]] = []
        for record in collector.list_records():
            if provider_id is not None and record.provider_selected != provider_id:
                continue
            if not _record_within_retention(record, cutoff):
                continue
            points.append(
                {
                    "timestamp": record.timestamp,
                    "latency_ms": record.duration_ms,
                    "provider_id": record.provider_selected,
                    "runtime_id": record.runtime_id,
                    "tool_name": record.tool_name,
                    "success": record.success,
                },
            )
        return {
            "provider_id": provider_id,
            "window_hours": hours,
            "point_count": len(points),
            "points": points,
        }

    def analytics_metadata(self) -> dict[str, Any]:
        """Export schema metadata for future analytics dashboards (P10B-1106)."""
        return {
            "schema": "titan.telemetry_analytics.v1",
            "persistence_schema": f"titan.provider_telemetry_persistence.v{SCHEMA_VERSION}",
            "retention_policy": self.retention_policy.value,
            "max_records": self.max_records,
            "query_apis": [
                "last_hour",
                "last_day",
                "provider_history",
                "latency_history",
                "correlate_with_run_store",
            ],
            "correlation_key": "runtime_id",
            "run_store_key": "run_id",
            "dimensions": [
                "provider_id",
                "tool_name",
                "execution_mode",
                "success",
                "fallback_used",
            ],
            "measures": ["latency_ms", "retry_count", "duration_ms"],
            "time_field": "timestamp",
        }

    def _historical_window(
        self,
        collector: ProviderTelemetryCollector,
        *,
        hours: int,
    ) -> dict[str, Any]:
        cutoff = _utc_now() - timedelta(hours=hours)
        records = [
            record
            for record in collector.list_records()
            if _record_within_retention(record, cutoff)
        ]
        transitions = [
            transition.to_dict()
            for transition in collector.snapshot().health_transitions
            if _parse_timestamp(transition.timestamp) is not None
            and _parse_timestamp(transition.timestamp) >= cutoff
        ]
        return {
            "window_hours": hours,
            "generated_at": _utc_now_iso(),
            "record_count": len(records),
            "records": [record.to_dict() for record in records],
            "health_transitions": transitions,
            "provider_stats": [
                stats.to_dict()
                for stats in collector.snapshot().provider_stats
            ],
        }

    def _retention_cutoff(self) -> datetime | None:
        seconds = _RETENTION_SECONDS.get(self.retention_policy)
        if seconds is None:
            return None
        return _utc_now() - timedelta(seconds=seconds)

    def _read_document(self) -> dict[str, Any]:
        """Load telemetry JSON with corruption recovery."""
        if not self.file_path.exists():
            return default_schema(retention_policy=self.retention_policy.value)
        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except json.JSONDecodeError:
            corrupt_path = self.file_path.with_suffix(f"{self.file_path.suffix}.corrupt.bak")
            shutil.copy2(self.file_path, corrupt_path)
            return default_schema(retention_policy=self.retention_policy.value)

        if not isinstance(raw, dict):
            return default_schema(retention_policy=self.retention_policy.value)

        raw.setdefault("schema_version", SCHEMA_VERSION)
        raw.setdefault("records", [])
        raw.setdefault("health_transitions", [])
        raw.setdefault("provider_stats", {})
        raw.setdefault(
            "aggregates",
            {"total_fallbacks": 0, "total_retries": 0, "total_failures": 0},
        )
        stored_policy = raw.get("retention_policy")
        if isinstance(stored_policy, str):
            raw["retention_policy"] = parse_retention_policy(stored_policy).value
        return raw

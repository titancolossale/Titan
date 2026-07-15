# =====================================
# Titan Telemetry Persistence Tests
# =====================================

"""Tests for Phase 10B Batch 11 — Telemetry Persistence & Retention (P10B-1101–P10B-1106)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.adapters.legacy_tool_adapter import register_legacy_tools
from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.capability_catalog import CapabilityCatalog
from tools.dependency_resolver import DependencyResolver
from tools.providers.provider_telemetry import (
    ProviderExecutionRecord,
    ProviderTelemetryCollector,
)
from tools.providers.telemetry_persistence import (
    TelemetryPersistenceManager,
    TelemetryRetentionPolicy,
    default_schema,
    parse_retention_policy,
)
from tools.tool_enums import ExecutionMode
from tools.tool_manager import ToolManager
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_run_store import ToolRunStore
from tools.tool_runtime import ToolRuntime
from tools.web_search_tool import WebSearchTool


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iso_hours_ago(hours: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).replace(microsecond=0).isoformat()


@pytest.fixture
def collector() -> ProviderTelemetryCollector:
    return ProviderTelemetryCollector()


@pytest.fixture
def persistence(tmp_path: Path) -> TelemetryPersistenceManager:
    return TelemetryPersistenceManager(
        file_path=tmp_path / "provider_telemetry.json",
        retention_policy=TelemetryRetentionPolicy.DAYS_7,
        persist=True,
        max_records=100,
    )


def _sample_record(
    *,
    runtime_id: str = "run-1",
    provider: str = "web_search",
    timestamp: str | None = None,
) -> ProviderExecutionRecord:
    return ProviderExecutionRecord(
        provider_selected=provider,
        duration_ms=12.5,
        provider_health="online",
        provider_version="0.1.0",
        success=True,
        retry_count=0,
        decision_id="dec-1",
        runtime_id=runtime_id,
        tool_name="web_search",
        timestamp=timestamp or _utc_now_iso(),
    )


def test_parse_retention_policy_values() -> None:
    """P10B-1102: Retention policy parser accepts configured values."""
    assert parse_retention_policy("24h") == TelemetryRetentionPolicy.HOURS_24
    assert parse_retention_policy("7d") == TelemetryRetentionPolicy.DAYS_7
    assert parse_retention_policy("30d") == TelemetryRetentionPolicy.DAYS_30
    assert parse_retention_policy("unlimited") == TelemetryRetentionPolicy.UNLIMITED
    assert parse_retention_policy("invalid") == TelemetryRetentionPolicy.DAYS_7


def test_save_and_load_snapshot(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1101: Telemetry snapshots persist to disk and reload."""
    collector.record(_sample_record(runtime_id="run-save"))
    persistence.save_snapshot(collector)

    restored = ProviderTelemetryCollector()
    assert persistence.load_snapshot(restored) is True
    assert len(restored.list_records()) == 1
    assert restored.list_records()[0].runtime_id == "run-save"


def test_reload_on_startup(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1103: Startup reload restores persisted telemetry."""
    collector.record(_sample_record(runtime_id="run-startup"))
    persistence.save_snapshot(collector)

    fresh = ProviderTelemetryCollector()
    assert persistence.reload_on_startup(fresh) is True
    assert fresh.list_records()[0].runtime_id == "run-startup"


def test_retention_compacts_old_records(
    collector: ProviderTelemetryCollector,
    tmp_path: Path,
) -> None:
    """P10B-1102: 24h retention removes stale records."""
    manager = TelemetryPersistenceManager(
        file_path=tmp_path / "telemetry.json",
        retention_policy=TelemetryRetentionPolicy.HOURS_24,
        persist=True,
    )
    collector.record(_sample_record(runtime_id="old", timestamp=_iso_hours_ago(48)))
    collector.record(_sample_record(runtime_id="new", timestamp=_iso_hours_ago(1)))
    removed = manager.compact_old_records(collector)
    assert removed == 1
    assert len(collector.list_records()) == 1
    assert collector.list_records()[0].runtime_id == "new"


def test_unlimited_retention_keeps_all_records(
    collector: ProviderTelemetryCollector,
    tmp_path: Path,
) -> None:
    """P10B-1102: Unlimited retention preserves historical records."""
    manager = TelemetryPersistenceManager(
        file_path=tmp_path / "telemetry.json",
        retention_policy=TelemetryRetentionPolicy.UNLIMITED,
        persist=True,
    )
    collector.record(_sample_record(runtime_id="ancient", timestamp=_iso_hours_ago(720)))
    removed = manager.compact_old_records(collector)
    assert removed == 0
    assert len(collector.list_records()) == 1


def test_rotate_history_archives_file(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1101: Rotation archives the current telemetry file."""
    collector.record(_sample_record())
    persistence.save_snapshot(collector)
    archive = persistence.rotate_history()
    assert archive is not None
    assert archive.exists()
    assert persistence.file_path.exists()


def test_corruption_recovery_returns_default(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1101: Corrupt JSON falls back to default schema."""
    persistence.file_path.parent.mkdir(parents=True, exist_ok=True)
    persistence.file_path.write_text("{not valid json", encoding="utf-8")
    assert persistence.load_snapshot(collector) is False
    assert collector.list_records() == []
    corrupt_backup = persistence.file_path.with_suffix(".json.corrupt.bak")
    assert corrupt_backup.exists()


def test_legacy_compat_missing_schema_fields(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """Backward compatibility: legacy telemetry JSON without new keys loads."""
    legacy_payload = {
        "records": [
            {
                "provider_selected": "web_search",
                "duration_ms": 5.0,
                "success": True,
                "runtime_id": "legacy-run",
            },
        ],
    }
    persistence.file_path.parent.mkdir(parents=True, exist_ok=True)
    persistence.file_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    assert persistence.load_snapshot(collector) is True
    assert collector.list_records()[0].runtime_id == "legacy-run"


def test_correlate_with_run_store(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
    tmp_path: Path,
) -> None:
    """P10B-1104: Telemetry correlates with ToolRunStore via runtime_id."""
    run_store = ToolRunStore(tmp_path / "runs.json", persist=True)
    collector.record(_sample_record(runtime_id="run-corr"))
    correlation = persistence.correlate_with_run_store(
        "run-corr",
        collector,
        run_store,
    )
    assert correlation["correlation_key"] == "runtime_id"
    assert correlation["record_count"] == 1
    assert correlation["telemetry_records"][0]["runtime_id"] == "run-corr"


def test_historical_api_last_hour_and_day(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1105: Historical query APIs filter by time window."""
    collector.record(_sample_record(timestamp=_iso_hours_ago(2)))
    collector.record(_sample_record(runtime_id="recent", timestamp=_iso_hours_ago(0)))
    hour = persistence.last_hour(collector)
    day = persistence.last_day(collector)
    assert hour["record_count"] == 1
    assert day["record_count"] == 2


def test_provider_history_and_latency_history(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """P10B-1105: Provider and latency history APIs return structured metadata."""
    collector.record(_sample_record(provider="web_search", runtime_id="r1"))
    collector.record(
        _sample_record(provider="brave_search", runtime_id="r2", timestamp=_iso_hours_ago(1)),
    )
    provider = persistence.provider_history("web_search", collector)
    latency = persistence.latency_history(collector, provider_id="web_search")
    assert provider["record_count"] == 1
    assert provider["aggregated_stats"]["provider_id"] == "web_search"
    assert latency["point_count"] == 1
    assert latency["points"][0]["latency_ms"] == 12.5


def test_analytics_metadata_export(persistence: TelemetryPersistenceManager) -> None:
    """P10B-1106: Analytics metadata exposes schema without dashboard UI."""
    metadata = persistence.analytics_metadata()
    assert metadata["schema"] == "titan.telemetry_analytics.v1"
    assert "last_hour" in metadata["query_apis"]
    assert metadata["correlation_key"] == "runtime_id"


def test_multiple_sessions_accumulate_records(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """Telemetry survives multiple save/load cycles across sessions."""
    collector.record(_sample_record(runtime_id="session-1"))
    persistence.save_snapshot(collector)

    session_two = ProviderTelemetryCollector()
    persistence.load_snapshot(session_two)
    session_two.record(_sample_record(runtime_id="session-2"))
    persistence.save_snapshot(session_two)

    final = ProviderTelemetryCollector()
    persistence.load_snapshot(final)
    run_ids = {record.runtime_id for record in final.list_records()}
    assert run_ids == {"session-1", "session-2"}


def test_runtime_persists_telemetry_across_restart(tmp_path: Path) -> None:
    """P10B-1103: ToolRuntime reloads telemetry after simulated restart."""
    telemetry_path = tmp_path / "provider_telemetry.json"
    audit_path = tmp_path / "audit.jsonl"
    reg = ToolRegistry()
    catalog = CapabilityCatalog()
    resolver = DependencyResolver()

    runtime_a = ToolRuntime(
        registry=reg,
        policy=ToolPolicy(),
        catalog=catalog,
        dependency_resolver=resolver,
        audit_logger=ToolAuditLogger(file_path=audit_path, enabled=False),
        persist_telemetry=True,
        telemetry_path=telemetry_path,
    )
    reg.register(WebSearchTool(provider_executor=runtime_a.provider_executor))
    register_legacy_tools(reg, catalog, resolver)
    runtime_a.refresh_catalog()

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="persist-session",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = runtime_a.invoke("web_search", {"query": "persist telemetry"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert telemetry_path.exists()

    runtime_b = ToolRuntime(
        registry=reg,
        policy=ToolPolicy(),
        catalog=catalog,
        dependency_resolver=resolver,
        audit_logger=ToolAuditLogger(file_path=audit_path, enabled=False),
        persist_telemetry=True,
        telemetry_path=telemetry_path,
    )
    assert runtime_b.provider_executor is not None
    assert len(runtime_b.provider_executor.telemetry.list_records()) >= 1


def test_tool_manager_historical_telemetry_api(tmp_path: Path) -> None:
    """P10B-1105: ToolManager exposes historical telemetry query methods."""
    manager = ToolManager(
        project_root=tmp_path,
        use_runtime_v2=True,
    )
    if manager.runtime is not None:
        manager.runtime.persist_telemetry = True
        manager.runtime.telemetry_path = tmp_path / "telemetry.json"
        manager.runtime.telemetry_persistence = TelemetryPersistenceManager(
            file_path=manager.runtime.telemetry_path,
            persist=True,
        )

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    manager.runtime.invoke("web_search", {"query": "history"}, ctx)

    assert manager.query_telemetry_last_hour()["record_count"] >= 1
    assert manager.query_telemetry_last_day()["record_count"] >= 1
    assert manager.query_provider_history("web_search")["record_count"] >= 1
    assert manager.query_latency_history(provider_id="web_search")["point_count"] >= 1
    metadata = manager.export_telemetry_analytics_metadata()
    assert metadata["schema"] == "titan.telemetry_analytics.v1"


def test_health_transitions_persist_and_reload(
    collector: ProviderTelemetryCollector,
    persistence: TelemetryPersistenceManager,
) -> None:
    """Health transitions survive persistence round-trip."""
    collector.record_health_transition("web_search", "online", "degraded", reason="rate_limit")
    collector.record(_sample_record())
    persistence.save_snapshot(collector)

    restored = ProviderTelemetryCollector()
    persistence.load_snapshot(restored)
    snapshot = restored.snapshot()
    assert len(snapshot.health_transitions) == 1
    assert snapshot.health_transitions[0].to_state == "degraded"


def test_default_schema_shape() -> None:
    """Default schema includes required persistence keys."""
    payload = default_schema()
    assert payload["schema_version"] == 1
    assert "records" in payload
    assert "aggregates" in payload

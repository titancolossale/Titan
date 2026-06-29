# =====================================
# Titan Tool Runtime Model Tests
# =====================================

"""Unit tests for Phase 10A foundation types (P10A-010)."""

from __future__ import annotations

import pytest

from core.exceptions import (
    ProviderUnavailable,
    ToolDependencyError,
    ToolError,
    ToolHealthError,
    ToolQuotaExceeded,
    TitanError,
)
from tools.provider_version import ProviderVersionInfo, _compare_versions
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, InvocationMode, RiskLevel, ToolHealthState
from tools.tool_dependency import DependencyGraph, ToolDependency
from tools.tool_metrics import MetricsCollector, ToolMetrics
from tools.tool_quota import QuotaTracker, UsageQuota
from tools.tool_run_models import (
    ToolExecutionContext,
    ToolRunOutcome,
    ToolRunStatus,
)
from tools.tool_result import ToolResult, ToolRunHandle
from tools.tool_schema import ToolParameter, ToolSchema


def test_tool_health_state_values() -> None:
    """P10A-003: health states cover operational spectrum."""
    assert ToolHealthState.ONLINE.value == "online"
    assert ToolHealthState.UNKNOWN.value == "unknown"
    assert len(ToolHealthState) == 5


def test_execution_mode_live_paper_simulation_mock() -> None:
    """P10A-003: environment execution modes are defined."""
    modes = {m.value for m in ExecutionMode}
    assert modes == {"live", "paper", "simulation", "mock"}


def test_invocation_mode_distinct_from_execution_mode() -> None:
    """P10A-003: transport and environment enums do not overlap."""
    invocation = {m.value for m in InvocationMode}
    execution = {m.value for m in ExecutionMode}
    assert invocation.isdisjoint(execution)


def test_tool_capability_from_schema() -> None:
    """P10A-003: legacy schema converts to ToolCapability."""
    params = [ToolParameter("query", "string", "Search query")]
    cap = ToolCapability.from_schema(
        "web_search",
        "Search the web",
        params,
        risk_level=RiskLevel.LOW,
        supported_execution_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    )
    assert cap.name == "web_search"
    assert cap.parameters[0].name == "query"
    assert ExecutionMode.MOCK in cap.supported_execution_modes


def test_tool_metrics_record_updates_counters() -> None:
    """P10A-004: metrics collector tracks success and failure."""
    collector = MetricsCollector()
    collector.record("time", duration_ms=100.0, success=True)
    collector.record("time", duration_ms=200.0, success=False)
    metrics = collector.get("time")
    assert metrics.execution_count == 2
    assert metrics.error_count == 1
    assert metrics.success_rate == 0.5
    assert metrics.average_runtime_ms == 150.0
    assert metrics.last_execution_at is not None


def test_tool_metrics_timeout_increments_both_counters() -> None:
    """P10A-004: timeout counts as error."""
    collector = MetricsCollector()
    collector.record("python_exec", duration_ms=5000.0, success=False, timed_out=True)
    metrics = collector.get("python_exec")
    assert metrics.timeout_count == 1
    assert metrics.error_count == 1


def test_tool_metrics_round_trip_dict() -> None:
    """P10A-004: metrics serialize and deserialize."""
    original = ToolMetrics(
        execution_count=3,
        average_runtime_ms=42.5,
        success_rate=0.67,
        error_count=1,
        timeout_count=0,
        last_execution_at="2026-06-28T12:00:00+00:00",
    )
    restored = ToolMetrics.from_dict(original.to_dict())
    assert restored == original


def test_provider_version_compatibility() -> None:
    """P10A-007: provider version compares against runtime version."""
    info = ProviderVersionInfo(
        provider_id="web_search",
        version="1.0.0",
        min_runtime_version="0.10.0",
        compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
    )
    assert info.is_compatible_with_runtime("0.10.0")
    assert info.is_compatible_with_runtime("0.11.0")
    assert not info.is_compatible_with_runtime("0.9.0")
    assert info.supports_mode(ExecutionMode.MOCK)
    assert not info.supports_mode(ExecutionMode.PAPER)


def test_compare_versions_semver_like() -> None:
    """P10A-007: version comparison handles semver segments."""
    assert _compare_versions("1.2.0", "1.1.9") > 0
    assert _compare_versions("0.10.0", "0.9.0") > 0
    assert _compare_versions("1.0.0", "1.0.0") == 0


def test_dependency_graph_detects_cycle() -> None:
    """P10A-005: circular tool dependencies fail at registration."""
    graph = DependencyGraph()
    graph.register_tool("a", (ToolDependency("tool", "b"),))
    with pytest.raises(ValueError, match="Circular dependency"):
        graph.register_tool("b", (ToolDependency("tool", "a"),))


def test_dependency_graph_check_unavailable_provider() -> None:
    """P10A-005: offline required dependency blocks execution."""
    graph = DependencyGraph()
    graph.register_tool(
        "web_search",
        (ToolDependency("provider", "web_search"),),
    )

    def is_registered(ref_type: str, ref_id: str) -> bool:
        return ref_type == "provider" and ref_id == "web_search"

    def health_lookup(ref_type: str, ref_id: str) -> ToolHealthState:
        return ToolHealthState.OFFLINE

    result = graph.check(
        "web_search",
        is_registered=is_registered,
        health_lookup=health_lookup,
    )
    assert not result.satisfied
    assert "indisponibles" in result.message


def test_quota_tracker_blocks_daily_limit() -> None:
    """P10A-006: daily quota enforcement when enabled."""
    tracker = QuotaTracker(enabled=True)
    quota = UsageQuota(max_invocations_per_day=1)
    assert tracker.check("time", quota).allowed
    tracker.record_finish("time", quota)
    assert not tracker.check("time", quota).allowed


def test_quota_tracker_disabled_allows_all() -> None:
    """P10A-006: quota checks pass when tracker disabled."""
    tracker = QuotaTracker(enabled=False)
    quota = UsageQuota(max_invocations_per_day=0)
    assert tracker.check("time", quota).allowed


def test_tool_run_outcome_terminal_states() -> None:
    """P10A-008: terminal vs pending confirmation outcomes."""
    pending = ToolRunOutcome(
        run_id="r1",
        status=ToolRunStatus.PENDING_CONFIRMATION,
        confirmation_request=None,
    )
    assert not pending.is_terminal()

    completed = ToolRunOutcome(
        run_id="r2",
        status=ToolRunStatus.COMPLETED,
        result=ToolResult(tool_name="time", success=True, data="now"),
    )
    assert completed.is_terminal()
    assert "[Source: time]" in completed.to_prompt_block()


def test_tool_execution_context_defaults() -> None:
    """P10A-008: execution context defaults to LIVE mode."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    assert ctx.execution_mode == ExecutionMode.LIVE
    assert not ctx.confirmed


def test_tool_result_backward_compatible_fields() -> None:
    """P10A-008: extended ToolResult keeps Phase 6 behavior."""
    result = ToolResult(tool_name="time", success=True, data="2026-01-01")
    assert result.run_id is None
    assert result.metadata == {}
    assert "2026-01-01" in result.format_for_prompt()


def test_tool_run_handle_fields() -> None:
    """P10A-008: async handle exposes run_id for polling."""
    handle = ToolRunHandle(run_id="abc", tool_name="web_search")
    assert handle.run_id == "abc"
    assert handle.poll_hint_seconds == 1.0


def test_tool_schema_extracted_module() -> None:
    """P10A-002: schema types live in dedicated module."""
    schema = ToolSchema(
        name="time",
        description="Current datetime",
        parameters=[],
    )
    assert schema.name == "time"


def test_exception_hierarchy() -> None:
    """P10A-001: tool errors inherit from TitanError."""
    assert issubclass(ToolError, TitanError)
    assert issubclass(ToolQuotaExceeded, ToolError)
    assert issubclass(ToolDependencyError, ToolError)
    assert issubclass(ToolHealthError, ToolError)
    assert issubclass(ProviderUnavailable, ToolError)


def test_metrics_collector_snapshot() -> None:
    """P10A-004: snapshot exports all tracked tools."""
    collector = MetricsCollector()
    collector.record("time", duration_ms=10.0, success=True)
    collector.record("file_read", duration_ms=20.0, success=True)
    snapshot = collector.snapshot()
    assert set(snapshot) == {"time", "file_read"}
    assert snapshot["time"]["execution_count"] == 1

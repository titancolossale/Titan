# =====================================
# Titan Tool Runtime Tests
# =====================================

"""Unit and integration tests for Phase 10A runtime core (P10A-019)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import ToolHealthError
from tools.adapters.legacy_tool_adapter import capability_from_tool, register_legacy_tools
from tools.capability_catalog import CapabilityCatalog
from tools.dependency_resolver import DependencyResolver
from tools.executors.sync_executor import SyncExecutor
from tools.health_monitor import HealthMonitor
from tools.permission_engine import PermissionEngine
from tools.retry_policy import RetryPolicy
from tools.time_tool import TimeTool
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_metrics import MetricsCollector
from tools.tool_policy import ToolPolicy
from tools.tool_quota import QuotaTracker, UsageQuota
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_runtime import ToolRuntime


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(TimeTool())
    return reg


@pytest.fixture
def runtime(registry: ToolRegistry) -> ToolRuntime:
    return ToolRuntime(registry=registry, policy=ToolPolicy())


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "sample.txt").write_text("data", encoding="utf-8")
    return tmp_path


def test_capability_catalog_registers_and_exports(runtime: ToolRuntime) -> None:
    """P10A-011: catalog lists legacy tools with metadata."""
    names = runtime.catalog.list_names()
    assert "time" in names
    exported = runtime.catalog.export()
    assert exported["time"]["risk_level"] == "safe"
    assert exported["time"]["invocation_mode"] == "sync"


def test_legacy_adapter_builds_capability_from_tool() -> None:
    """P10A-014: BaseTool schema maps to ToolCapability."""
    cap = capability_from_tool(TimeTool())
    assert cap.name == "time"
    assert ExecutionMode.MOCK in cap.supported_execution_modes
    assert cap.risk_level.value == "safe"


def test_health_monitor_blocks_offline_tool(runtime: ToolRuntime) -> None:
    """P10A-012: OFFLINE health prevents execution."""
    runtime.health_monitor.set_tool_health("time", ToolHealthState.OFFLINE)
    cap = runtime.catalog.get("time")
    assert cap is not None
    with pytest.raises(ToolHealthError):
        runtime.health_monitor.assert_ready("time", cap)


def test_health_monitor_allows_degraded(runtime: ToolRuntime) -> None:
    """P10A-012: DEGRADED health allows execution with notice."""
    runtime.health_monitor.set_tool_health("time", ToolHealthState.DEGRADED)
    cap = runtime.catalog.get("time")
    assert cap is not None
    result = runtime.health_monitor.assert_ready("time", cap)
    assert result.allowed
    assert "dégradé" in result.message


def test_health_monitor_offline_to_online_hysteresis() -> None:
    """P10A-012: cooldown delays OFFLINE→ONLINE transition."""
    monitor = HealthMonitor(offline_cooldown_seconds=3600.0)
    monitor.set_tool_health("time", ToolHealthState.OFFLINE)
    monitor.set_tool_health("time", ToolHealthState.ONLINE)
    assert monitor.get_tool_health("time") == ToolHealthState.OFFLINE


def test_dependency_resolver_blocks_offline_provider(runtime: ToolRuntime) -> None:
    """P10A-013: offline provider dependency fails check."""
    runtime.health_monitor.set_provider_health("web_search", ToolHealthState.OFFLINE)
    reg = ToolRegistry()
    reg.register(TimeTool())
    from tools.web_search_tool import WebSearchTool

    reg.register(WebSearchTool())
    catalog = CapabilityCatalog()
    resolver = DependencyResolver(health_monitor=runtime.health_monitor)
    register_legacy_tools(reg, catalog, resolver)
    result = resolver.check("web_search", registry=reg)
    assert not result.satisfied


def test_permission_engine_denies_unlisted_caller(project_root: Path) -> None:
    """P10A-016: caller allowlist enforced by permission engine."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    assert manager.runtime is not None
    cap = manager.runtime.catalog.get("file_write")
    assert cap is not None
    ctx = ToolExecutionContext(
        caller="research",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    result = manager.runtime.permission_engine.evaluate("file_write", cap, ctx)
    assert not result.allowed


def test_permission_engine_allows_brain(runtime: ToolRuntime) -> None:
    """P10A-016: brain caller passes permission for time."""
    cap = runtime.catalog.get("time")
    assert cap is not None
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    result = runtime.permission_engine.evaluate("time", cap, ctx)
    assert result.allowed


def test_permission_engine_does_not_gate_confirmation(runtime: ToolRuntime) -> None:
    """P10A-020: confirmation is ConfirmationGate responsibility, not PermissionEngine."""
    cap = runtime.catalog.get("time")
    assert cap is not None
    from dataclasses import replace

    high_cap = replace(cap, risk_level=RiskLevel.HIGH)
    brain_ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        confirmed=False,
    )
    brain_result = runtime.permission_engine.evaluate("time", high_cap, brain_ctx)
    assert brain_result.allowed

    pending = runtime.confirmation_gate.evaluate("time", high_cap, brain_ctx, {})
    assert not pending.satisfied
    assert pending.request is not None


def test_retry_policy_retries_transient_errors() -> None:
    """P10A-017: transient timeout errors trigger retry."""
    policy = RetryPolicy()
    result = ToolResult(tool_name="x", success=False, error="connection timeout")
    assert policy.should_retry(1, 2, result)
    assert policy.delay_seconds(2) > policy.delay_seconds(1)


def test_retry_policy_skips_permanent_errors() -> None:
    """P10A-017: validation errors do not retry."""
    policy = RetryPolicy()
    result = ToolResult(tool_name="x", success=False, error="Paramètre invalide")
    assert not policy.should_retry(1, 3, result)


def test_sync_executor_runs_time_tool(registry: ToolRegistry) -> None:
    """P10A-015: sync executor delegates to registry."""
    executor = SyncExecutor(registry=registry)
    result = executor.execute("time", {})
    assert result.success
    assert len(result.data) >= 10


def test_runtime_invoke_success(runtime: ToolRuntime) -> None:
    """P10A-018: invoke completes time tool with metrics."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("time", {}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.success
    metrics = runtime.metrics_collector.get("time")
    assert metrics.execution_count == 1


def test_runtime_invoke_unknown_tool(runtime: ToolRuntime) -> None:
    """P10A-018: unknown tool returns FAILED outcome."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("missing", {}, ctx)
    assert outcome.status == ToolRunStatus.FAILED
    assert "inconnu" in outcome.error.lower()


def test_runtime_invoke_blocks_offline(runtime: ToolRuntime) -> None:
    """P10A-018: offline tool blocked at preflight."""
    runtime.health_monitor.set_tool_health("time", ToolHealthState.OFFLINE)
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("time", {}, ctx)
    assert outcome.status == ToolRunStatus.FAILED
    assert "hors ligne" in outcome.error.lower()


def test_runtime_quota_enforcement(runtime: ToolRuntime) -> None:
    """P10A-018: quota exceeded blocks invocation."""
    runtime.quota_tracker.enabled = True
    cap = runtime.catalog.get("time")
    assert cap is not None
    from dataclasses import replace

    limited = replace(cap, quota=UsageQuota(max_invocations_per_day=1))
    runtime.catalog._capabilities["time"] = limited
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    runtime.invoke("time", {}, ctx)
    outcome = runtime.invoke("time", {}, ctx)
    assert outcome.status == ToolRunStatus.FAILED
    assert "quota" in outcome.error.lower()


def test_runtime_outcome_to_result(runtime: ToolRuntime) -> None:
    """P10A-018: outcome converts to legacy ToolResult."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("time", {}, ctx)
    result = runtime.outcome_to_result(outcome)
    assert result.success
    assert result.run_id == outcome.run_id


def test_tool_manager_v2_flag_uses_runtime(project_root: Path) -> None:
    """P10A-018: use_runtime_v2 routes run() through ToolRuntime."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    result = manager.run("time", caller="brain")
    assert result.success
    assert manager.runtime is not None
    assert manager.runtime.metrics_collector.get("time").execution_count == 1


def test_tool_manager_v2_enabled_by_default(project_root: Path) -> None:
    """P10A-029: Tool Runtime V2 is the default composition-root path."""
    manager = ToolManager(project_root=project_root)
    assert manager.runtime is not None
    result = manager.run("time", caller="brain")
    assert result.success
    assert result.run_id is not None


def test_tool_manager_legacy_path_opt_out(project_root: Path) -> None:
    """P10A-029: Phase 6 direct-registry path available via explicit opt-out."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=False)
    assert manager.runtime is None
    result = manager.run("time", caller="brain")
    assert result.success
    assert result.run_id is None


def test_tool_manager_invoke_returns_outcome(project_root: Path) -> None:
    """P10A-018: invoke() exposes full ToolRunOutcome."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=False)
    outcome = manager.invoke("time", caller="brain")
    assert outcome.is_terminal()
    assert outcome.status == ToolRunStatus.COMPLETED


def test_capability_catalog_export_with_metrics(runtime: ToolRuntime) -> None:
    """P10A-011: export merges metrics snapshot."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    runtime.invoke("time", {}, ctx)
    exported = runtime.catalog.export(
        metrics_snapshot=runtime.metrics_collector.snapshot()
    )
    assert exported["time"]["metrics"]["execution_count"] == 1


def test_register_legacy_tools_idempotent(registry: ToolRegistry) -> None:
    """P10A-014: repeated registration does not raise."""
    catalog = CapabilityCatalog()
    resolver = DependencyResolver()
    register_legacy_tools(registry, catalog, resolver)
    register_legacy_tools(registry, catalog, resolver)
    assert catalog.get("time") is not None

# =====================================
# Titan Tool Persistence and Async Tests
# =====================================

"""Integration tests for Batch 4 persistence, audit, and async foundation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.executors.async_executor import AsyncExecutor
from tools.executors.sync_executor import SyncExecutor
from tools.time_tool import TimeTool
from tools.tool_enums import InvocationMode
from tools.tool_metrics import MetricsCollector
from tools.tool_policy import ToolPolicy
from tools.tool_quota import QuotaTracker
from tools.tool_registry import ToolRegistry
from tools.tool_run_models import ToolExecutionContext, ToolRun, ToolRunStatus
from tools.tool_run_store import ToolRunStore
from tools.tool_runtime import ToolRuntime


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(TimeTool())
    return reg


@pytest.fixture
def runtime_with_persistence(tmp_path: Path, registry: ToolRegistry) -> ToolRuntime:
    audit_path = tmp_path / "audit.jsonl"
    runs_path = tmp_path / "runs.json"
    metrics_path = tmp_path / "metrics.json"
    return ToolRuntime(
        registry=registry,
        policy=ToolPolicy(),
        run_store=ToolRunStore(runs_path, persist=True),
        audit_logger=ToolAuditLogger(file_path=audit_path, enabled=True),
        persist_runs=True,
        persist_metrics=True,
        metrics_path=metrics_path,
    )


def test_runtime_audit_logs_sync_execution(runtime_with_persistence: ToolRuntime) -> None:
    """P10A-023: successful sync invoke emits invoked/started/completed audit events."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime_with_persistence.invoke("time", {}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert runtime_with_persistence.audit_logger is not None
    types = [event.event_type for event in runtime_with_persistence.audit_logger.events()]
    assert "invoked" in types
    assert "started" in types
    assert "completed" in types


def test_runtime_persists_run_record(runtime_with_persistence: ToolRuntime) -> None:
    """P10A-024: completed runs are stored and retrievable."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime_with_persistence.invoke("time", {}, ctx)
    stored = runtime_with_persistence.get_run(outcome.run_id)
    assert stored is not None
    assert stored.status == ToolRunStatus.COMPLETED


def test_runtime_persists_metrics_snapshot(
    runtime_with_persistence: ToolRuntime, tmp_path: Path
) -> None:
    """P10A-004: metrics snapshot persists to disk when enabled."""
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    runtime_with_persistence.invoke("time", {}, ctx)
    assert runtime_with_persistence.metrics_path.exists()
    metrics, _quota = MetricsCollector.load_persisted(runtime_with_persistence.metrics_path)
    assert metrics["time"]["execution_count"] == 1


def test_async_executor_runs_in_background(registry: ToolRegistry) -> None:
    """P10A-026: async executor completes work on thread pool."""
    from tools.cancellation_registry import CancellationRegistry

    sync = SyncExecutor(registry=registry)
    registry_obj = CancellationRegistry()
    executor = AsyncExecutor(sync_executor=sync, cancellation_registry=registry_obj)
    future = executor.submit("run-async", "time", {})
    result = future.result(timeout=5)
    assert result.success
    executor.shutdown(wait=True)


def test_runtime_async_invocation_queues_and_polls(registry: ToolRegistry) -> None:
    """P10A-026: ASYNC capability returns QUEUED then poll_run completes."""
    runtime = ToolRuntime(registry=registry, policy=ToolPolicy())
    cap = runtime.catalog.get("time")
    assert cap is not None
    async_cap = replace(cap, invocation_mode=InvocationMode.ASYNC)
    runtime.catalog._capabilities["time"] = async_cap

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("time", {}, ctx)
    assert outcome.status == ToolRunStatus.QUEUED

    polled = runtime.poll_run(outcome.run_id, timeout=5)
    assert polled.status == ToolRunStatus.COMPLETED
    assert polled.result is not None
    assert polled.result.success
    runtime.async_executor.shutdown(wait=True)  # type: ignore[union-attr]


def test_runtime_cancel_run_marks_running_run_cancelled(registry: ToolRegistry) -> None:
    """P10A-025: cancel_run marks an in-flight run cancelled and audits."""
    runtime = ToolRuntime(registry=registry, policy=ToolPolicy())
    run_id = "run-cancel-test"
    running = ToolRun(
        run_id=run_id,
        tool_name="time",
        status=ToolRunStatus.RUNNING,
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    assert runtime.run_store is not None
    runtime.run_store.upsert(running)

    cancelled = runtime.cancel_run(run_id, reason="Test annulation")
    assert cancelled
    stored = runtime.get_run(run_id)
    assert stored is not None
    assert stored.status == ToolRunStatus.CANCELLED
    types = [event.event_type for event in runtime.audit_logger.events()]  # type: ignore[union-attr]
    assert "cancelled" in types


def test_runtime_cancel_run_rejects_terminal_run(registry: ToolRegistry) -> None:
    """P10A-025: cancel_run returns False for completed runs."""
    runtime = ToolRuntime(registry=registry, policy=ToolPolicy())
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("time", {}, ctx)
    assert not runtime.cancel_run(outcome.run_id)


def test_metrics_and_quota_snapshot_round_trip() -> None:
    """P10A-006: quota usage snapshot restores counters."""
    tracker = QuotaTracker(enabled=True)
    tracker.record_start("time")
    tracker.record_finish("time", None)
    snapshot = tracker.usage_snapshot()
    restored = QuotaTracker(enabled=True)
    restored.load_snapshot(snapshot)
    assert restored.usage_snapshot()["time"]["concurrent_active"] == 0

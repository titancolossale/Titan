# =====================================
# Titan Tool Run Store Tests
# =====================================

"""Unit tests for tool run persistence (Phase 10A — P10A-027)."""

from __future__ import annotations

from pathlib import Path

from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolRun, ToolRunStatus
from tools.tool_run_store import ToolRunStore, tool_run_from_dict, tool_run_to_dict


def test_tool_run_round_trip_serialization() -> None:
    """P10A-024: ToolRun serializes to JSON-compatible dict."""
    run = ToolRun(
        run_id="run-1",
        tool_name="time",
        status=ToolRunStatus.COMPLETED,
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.LIVE,
        health_state=ToolHealthState.ONLINE,
        result=ToolResult(tool_name="time", success=True, data="2026", source="time"),
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )
    restored = tool_run_from_dict(tool_run_to_dict(run))
    assert restored.run_id == run.run_id
    assert restored.status == ToolRunStatus.COMPLETED
    assert restored.result is not None
    assert restored.result.success


def test_tool_run_store_persists_to_disk(tmp_path: Path) -> None:
    """P10A-024: upsert writes runs to JSON when persist=True."""
    store_path = tmp_path / "tool_runs.json"
    store = ToolRunStore(store_path, persist=True)
    run = ToolRun(
        run_id="run-2",
        tool_name="time",
        status=ToolRunStatus.RUNNING,
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    store.upsert(run)
    assert store_path.exists()

    reloaded = ToolRunStore(store_path, persist=True)
    loaded = reloaded.get("run-2")
    assert loaded is not None
    assert loaded.status == ToolRunStatus.RUNNING


def test_tool_run_store_in_memory_without_persist() -> None:
    """P10A-024: in-memory store works without disk writes."""
    store = ToolRunStore(persist=False)
    run = ToolRun(
        run_id="run-3",
        tool_name="time",
        status=ToolRunStatus.FAILED,
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        error="test",
    )
    store.upsert(run)
    assert store.get("run-3") is not None

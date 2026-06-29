# =====================================
# Titan Tool Run Store
# =====================================

"""JSON persistence for tool run lifecycle records (Phase 10A — P10A-024)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config.settings import TOOL_RUNS_PATH
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_result import ToolResult
from tools.tool_run_models import ToolEvent, ToolRun, ToolRunStatus

SCHEMA_VERSION = 1


def default_schema() -> dict[str, Any]:
    """Return empty tool runs document."""
    return {"schema_version": SCHEMA_VERSION, "runs": []}


def _result_to_dict(result: ToolResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "tool_name": result.tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "source": result.source,
        "run_id": result.run_id,
        "metadata": dict(result.metadata),
    }


def _result_from_dict(data: dict[str, Any] | None) -> ToolResult | None:
    if not data:
        return None
    return ToolResult(
        tool_name=str(data.get("tool_name", "")),
        success=bool(data.get("success", False)),
        data=str(data.get("data", "")),
        error=str(data.get("error", "")),
        source=str(data.get("source", "")),
        run_id=data.get("run_id"),
        metadata=dict(data.get("metadata") or {}),
    )


def _event_to_dict(event: ToolEvent) -> dict[str, Any]:
    return asdict(event)


def _event_from_dict(data: dict[str, Any]) -> ToolEvent:
    return ToolEvent(
        run_id=str(data.get("run_id", "")),
        event_type=str(data.get("event_type", "")),
        payload=str(data.get("payload", "")),
        sequence=int(data.get("sequence", 0)),
    )


def tool_run_to_dict(run: ToolRun) -> dict[str, Any]:
    """Serialize a ToolRun for JSON persistence."""
    return {
        "run_id": run.run_id,
        "tool_name": run.tool_name,
        "status": run.status.value,
        "caller": run.caller,
        "user": run.user,
        "session_id": run.session_id,
        "turn_id": run.turn_id,
        "execution_mode": run.execution_mode.value,
        "health_state": run.health_state.value,
        "result": _result_to_dict(run.result),
        "events": [_event_to_dict(event) for event in run.events],
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def tool_run_from_dict(data: dict[str, Any]) -> ToolRun:
    """Restore a ToolRun from persisted JSON."""
    try:
        status = ToolRunStatus(str(data.get("status", ToolRunStatus.FAILED.value)))
    except ValueError:
        status = ToolRunStatus.FAILED
    try:
        execution_mode = ExecutionMode(str(data.get("execution_mode", ExecutionMode.LIVE.value)))
    except ValueError:
        execution_mode = ExecutionMode.LIVE
    try:
        health_state = ToolHealthState(str(data.get("health_state", ToolHealthState.UNKNOWN.value)))
    except ValueError:
        health_state = ToolHealthState.UNKNOWN

    return ToolRun(
        run_id=str(data.get("run_id", "")),
        tool_name=str(data.get("tool_name", "")),
        status=status,
        caller=str(data.get("caller", "")),
        user=str(data.get("user", "")),
        session_id=str(data.get("session_id", "")),
        turn_id=str(data.get("turn_id", "")),
        execution_mode=execution_mode,
        health_state=health_state,
        result=_result_from_dict(data.get("result")),
        events=[_event_from_dict(item) for item in data.get("events") or []],
        error=str(data.get("error", "")),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
    )


class ToolRunStore:
    """In-memory tool run index with optional JSON persistence."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        persist: bool = False,
    ) -> None:
        self.file_path = Path(file_path or TOOL_RUNS_PATH)
        self.persist = persist
        self._data = self.load() if persist else default_schema()
        self._index: dict[str, ToolRun] = {}
        for item in self._data.get("runs", []):
            run = tool_run_from_dict(item)
            self._index[run.run_id] = run

    def load(self) -> dict[str, Any]:
        """Load runs from disk."""
        if not self.file_path.exists():
            return default_schema()
        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        raw.setdefault("schema_version", SCHEMA_VERSION)
        raw.setdefault("runs", [])
        return raw

    def save(self) -> None:
        """Persist runs to disk when persistence is enabled."""
        if not self.persist:
            return
        self._data["runs"] = [tool_run_to_dict(run) for run in self._index.values()]
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, indent=4, ensure_ascii=False)

    def upsert(self, run: ToolRun) -> ToolRun:
        """Insert or replace a run and optionally persist."""
        self._index[run.run_id] = run
        if self.persist:
            self.save()
        return run

    def get(self, run_id: str) -> ToolRun | None:
        """Return a run by id."""
        return self._index.get(run_id)

    def list_runs(self, *, session_id: str | None = None) -> list[ToolRun]:
        """Return all runs, optionally filtered by session."""
        runs = list(self._index.values())
        if session_id is None:
            return runs
        return [run for run in runs if run.session_id == session_id]

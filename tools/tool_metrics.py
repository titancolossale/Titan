# =====================================
# Titan Tool Metrics
# =====================================

"""Execution metrics for tool observability (Phase 10A — P10A-004)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METRICS_SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ToolMetrics:
    """Rolling execution statistics for a single tool."""

    execution_count: int = 0
    average_runtime_ms: float = 0.0
    success_rate: float = 1.0
    error_count: int = 0
    timeout_count: int = 0
    last_execution_at: str | None = None

    def to_dict(self) -> dict:
        """Serialize metrics for persistence or dashboard export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ToolMetrics:
        """Restore metrics from a persisted snapshot."""
        return cls(
            execution_count=int(data.get("execution_count", 0)),
            average_runtime_ms=float(data.get("average_runtime_ms", 0.0)),
            success_rate=float(data.get("success_rate", 1.0)),
            error_count=int(data.get("error_count", 0)),
            timeout_count=int(data.get("timeout_count", 0)),
            last_execution_at=data.get("last_execution_at"),
        )


@dataclass
class MetricsCollector:
    """In-memory metrics aggregator with optional persistence (Batch 4)."""

    _by_tool: dict[str, ToolMetrics] = field(default_factory=dict)

    def get(self, tool_name: str) -> ToolMetrics:
        """Return metrics for a tool, creating an empty record if needed."""
        if tool_name not in self._by_tool:
            self._by_tool[tool_name] = ToolMetrics()
        return self._by_tool[tool_name]

    def record(
        self,
        tool_name: str,
        *,
        duration_ms: float,
        success: bool,
        timed_out: bool = False,
    ) -> ToolMetrics:
        """Update rolling metrics after a terminal run."""
        metrics = self.get(tool_name)
        prev_count = metrics.execution_count
        new_count = prev_count + 1

        if prev_count == 0:
            metrics.average_runtime_ms = duration_ms
        else:
            metrics.average_runtime_ms = (
                (metrics.average_runtime_ms * prev_count) + duration_ms
            ) / new_count

        metrics.execution_count = new_count
        metrics.last_execution_at = _utc_now_iso()

        if timed_out:
            metrics.timeout_count += 1
            metrics.error_count += 1
        elif not success:
            metrics.error_count += 1

        successes = new_count - metrics.error_count
        metrics.success_rate = successes / new_count if new_count else 1.0
        return metrics

    def snapshot(self) -> dict[str, dict]:
        """Export all tool metrics as a JSON-serializable dict."""
        return {name: m.to_dict() for name, m in self._by_tool.items()}

    def load_snapshot(self, metrics: dict[str, dict]) -> None:
        """Restore metrics from a persisted snapshot."""
        for name, data in metrics.items():
            self._by_tool[name] = ToolMetrics.from_dict(data)

    def persist(self, file_path: Path, *, quota_usage: dict[str, dict] | None = None) -> None:
        """Write metrics (and optional quota usage) to disk."""
        payload: dict[str, Any] = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "metrics": self.snapshot(),
        }
        if quota_usage is not None:
            payload["quota_usage"] = quota_usage
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

    @staticmethod
    def load_persisted(file_path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
        """Load metrics and quota usage from a persisted file."""
        if not file_path.exists():
            return {}, {}
        with file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        return dict(raw.get("metrics") or {}), dict(raw.get("quota_usage") or {})

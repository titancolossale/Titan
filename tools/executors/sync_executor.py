# =====================================
# Titan Sync Executor
# =====================================

"""Synchronous tool execution via registry (Phase 10A — P10A-015)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolResult


@dataclass
class SyncExecutor:
    """Execute tools synchronously through the tool registry."""

    registry: ToolRegistry

    def execute(
        self,
        tool_name: str,
        params: dict | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        """Run a tool and optionally enforce a timeout budget.

        Timeout enforcement delegates to tool-internal handling when present;
        the executor records elapsed time for metrics either way.
        """
        start = time.perf_counter()
        result = self.registry.run(tool_name, params)
        elapsed = time.perf_counter() - start

        if timeout_seconds is not None and elapsed > timeout_seconds and result.success:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Timeout dépassé ({timeout_seconds}s).",
                source=tool_name,
            )
        return result

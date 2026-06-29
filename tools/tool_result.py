# =====================================
# Titan Tool Result
# =====================================

"""Structured tool execution results with source attribution (Phase 6 — P6-010)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolRequest:
    """Validated tool invocation request produced by Brain reasoning/executor."""

    tool_name: str
    params: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """Outcome of a single tool execution — consumed by Brain prompt assembly."""

    tool_name: str
    success: bool
    data: str = ""
    error: str = ""
    source: str = ""
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def format_for_prompt(self) -> str:
        """Format with explicit source attribution (Constitution 9.3)."""
        attribution = self.source or self.tool_name
        if self.success:
            body = self.data.strip() or "(aucune donnée)"
            return f"[Source: {attribution}]\n{body}"
        return f"[Source: {attribution}] ERREUR: {self.error.strip() or 'échec inconnu'}"


@dataclass(frozen=True)
class ToolRunHandle:
    """Handle returned for async or background tool runs (Phase 10A)."""

    run_id: str
    tool_name: str
    poll_hint_seconds: float = 1.0

# =====================================
# Titan Tool Orchestration Models
# =====================================

"""Structured orchestration artifacts for Phase 12.6 Batch 1 (P126-001)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tools.permission_manager import PermissionLevel
from tools.tool_result import ToolResult


class OrchestrationStatus(str, Enum):
    """Lifecycle status for a tool orchestration attempt."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    PENDING_CONFIRMATION = "pending_confirmation"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class InterpretedToolRequest:
    """An interpreted user request ready for orchestrated tool execution."""

    tool_name: str
    params: dict = field(default_factory=dict)
    message: str = ""
    selected_action: str | None = None
    caller: str = "brain"


@dataclass(frozen=True)
class ToolOrchestrationResult:
    """Structured outcome from ToolOrchestrator (P126-001)."""

    orchestration_status: OrchestrationStatus
    selected_tool: str | None
    selected_action: str | None
    permission_level: PermissionLevel
    executed: bool
    confirmation_required: bool
    reason: str
    result: ToolResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging and tests."""
        return {
            "orchestration_status": self.orchestration_status.value,
            "selected_tool": self.selected_tool,
            "selected_action": self.selected_action,
            "permission_level": self.permission_level.value,
            "executed": self.executed,
            "confirmation_required": self.confirmation_required,
            "reason": self.reason,
            "result_success": self.result.success if self.result is not None else None,
        }

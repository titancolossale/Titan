# =====================================
# Titan Execution Tool Models
# =====================================

"""Normalized types for the Phase 18.3 Tool Execution Bridge.

The bridge sits between ExecutionSafety approval and the Tool Registry.
Results are public metadata only — never raw tool payloads or exception
objects for LLM consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class BridgeExecutionStatus(str, Enum):
    """Normalized outcome of one Tool Execution Bridge dispatch."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    FORBIDDEN = "FORBIDDEN"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


# Structured diagnostics emitted by the bridge (log event prefixes).
DIAG_TOOL_DISPATCH = "TOOL_DISPATCH"
DIAG_TOOL_STARTED = "TOOL_STARTED"
DIAG_TOOL_COMPLETED = "TOOL_COMPLETED"
DIAG_TOOL_FAILED = "TOOL_FAILED"
DIAG_TOOL_TIMEOUT = "TOOL_TIMEOUT"
DIAG_TOOL_CANCELLED = "TOOL_CANCELLED"
DIAG_TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"


@dataclass(frozen=True)
class ToolBridgeRequest:
    """Resolved tool invocation request (registry ids only — no hardcoded names)."""

    tool_id: str
    action_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    permission_id: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Public metadata for diagnostics — never includes raw parameter values."""
        return {
            "tool_id": self.tool_id,
            "action_id": self.action_id,
            "parameter_keys": sorted(str(k) for k in self.parameters.keys()),
            "requires_confirmation": self.requires_confirmation,
            "permission_id": self.permission_id,
        }


@dataclass(frozen=True)
class BridgeExecutionResult:
    """Normalized bridge outcome (Phase 18.3–18.4 ExecutionResult contract)."""

    status: BridgeExecutionStatus
    message: str
    success: bool
    duration: float = 0.0
    tool_id: str | None = None
    action_id: str | None = None
    error: str | None = None
    blocked_reason: str | None = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Concise public summary only — never raw tool data / exceptions.
    result_summary: str | None = None
    # Phase 18.4 — reversible / rollback hints from the tool (public only).
    reversible: bool = False
    rollback_token: str | None = None

    @property
    def execution_result(self) -> str:
        """Prompt-safe execution result text."""
        if self.result_summary:
            return self.result_summary
        if self.error:
            return self.error
        if self.blocked_reason:
            return self.blocked_reason
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "success": self.success,
            "duration": round(float(self.duration), 4),
            "tool_id": self.tool_id,
            "action_id": self.action_id,
            "error": self.error,
            "blocked_reason": self.blocked_reason,
            "result_summary": self.result_summary,
            "completed_at": self.completed_at.isoformat(),
            "reversible": self.reversible,
            "rollback_token": self.rollback_token,
        }

    def format_for_prompt(self) -> str:
        """Prompt block — Last Tool / Execution Status / Execution Result only."""
        return "\n".join(
            [
                f"Last Tool: {self.tool_id or 'None'}",
                f"Execution Status: {self.status.value}",
                f"Execution Result: {self.execution_result}",
            ]
        )

    @classmethod
    def cognitive_success(
        cls,
        *,
        message: str,
        duration: float = 0.0,
        now: datetime | None = None,
    ) -> BridgeExecutionResult:
        """Non-tool next-action registered successfully (no registry dispatch)."""
        return cls(
            status=BridgeExecutionStatus.SUCCESS,
            message=message,
            success=True,
            duration=max(0.0, float(duration)),
            result_summary=message,
            completed_at=now or datetime.now(timezone.utc),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        tool_id: str | None,
        reason: str,
        duration: float = 0.0,
        now: datetime | None = None,
    ) -> BridgeExecutionResult:
        return cls(
            status=BridgeExecutionStatus.FAILED,
            message=reason,
            success=False,
            duration=max(0.0, float(duration)),
            tool_id=tool_id,
            error=reason,
            result_summary=reason,
            completed_at=now or datetime.now(timezone.utc),
        )

    @classmethod
    def from_exception(
        cls,
        *,
        tool_id: str | None,
        action_id: str | None,
        exc: BaseException,
        duration: float = 0.0,
        now: datetime | None = None,
    ) -> BridgeExecutionResult:
        """Normalize an unexpected failure — never expose raw exception objects."""
        safe = _normalize_error_message(exc)
        return cls(
            status=BridgeExecutionStatus.FAILED,
            message=f"Tool execution failed: {safe}",
            success=False,
            duration=max(0.0, float(duration)),
            tool_id=tool_id,
            action_id=action_id,
            error=safe,
            result_summary=safe,
            completed_at=now or datetime.now(timezone.utc),
        )


def _normalize_error_message(exc: BaseException) -> str:
    """Turn an exception into a short public string (no traceback / type dump)."""
    text = str(exc).strip() or type(exc).__name__
    # Collapse whitespace; cap length for prompt safety.
    text = " ".join(text.split())
    if len(text) > 240:
        return text[:237] + "..."
    return text

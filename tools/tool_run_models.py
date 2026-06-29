# =====================================
# Titan Tool Run Models
# =====================================

"""Tool run lifecycle types for the Phase 10A runtime (P10A-008)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.tool_result import ToolResult


class ToolRunStatus(str, Enum):
    """Lifecycle status for a single tool invocation."""

    PENDING_CONFIRMATION = "pending_confirmation"
    QUEUED = "queued"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class ToolExecutionContext:
    """Per-invocation context passed through the tool runtime."""

    caller: str
    user: str
    session_id: str
    turn_id: str
    confirmed: bool = False
    confirmation_token: str | None = None
    dry_run: bool = False
    execution_mode: ExecutionMode = ExecutionMode.LIVE
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolEvent:
    """Streaming chunk emitted during a tool run."""

    run_id: str
    event_type: str
    payload: str = ""
    sequence: int = 0


@dataclass(frozen=True)
class ConfirmationRequest:
    """User confirmation prompt for a gated tool invocation."""

    token: str
    tool_name: str
    description: str
    params_digest: str = ""


@dataclass
class ToolRun:
    """Persistent record of a tool invocation."""

    run_id: str
    tool_name: str
    status: ToolRunStatus
    caller: str
    user: str
    session_id: str
    turn_id: str
    execution_mode: ExecutionMode = ExecutionMode.LIVE
    health_state: ToolHealthState = ToolHealthState.UNKNOWN
    result: ToolResult | None = None
    events: list[ToolEvent] = field(default_factory=list)
    error: str = ""
    started_at: str | None = None
    finished_at: str | None = None

    def is_terminal(self) -> bool:
        """Return True when the run has reached a final state."""
        return self.status in {
            ToolRunStatus.COMPLETED,
            ToolRunStatus.FAILED,
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }


@dataclass
class ToolRunOutcome:
    """Runtime boundary result consumed by ToolDispatcher."""

    run_id: str
    status: ToolRunStatus
    result: ToolResult | None = None
    events: list[ToolEvent] = field(default_factory=list)
    confirmation_request: ConfirmationRequest | None = None
    error: str = ""

    def is_terminal(self) -> bool:
        """Return True when no further polling or confirmation is needed."""
        if self.status == ToolRunStatus.PENDING_CONFIRMATION:
            return False
        return self.status in {
            ToolRunStatus.COMPLETED,
            ToolRunStatus.FAILED,
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }

    def to_prompt_block(self) -> str:
        """Format outcome for Brain prompt injection."""
        if self.confirmation_request is not None:
            return (
                f"[Confirmation requise: {self.confirmation_request.tool_name}] "
                f"{self.confirmation_request.description}"
            )
        if self.result is not None:
            return self.result.format_for_prompt()
        if self.error:
            return f"[Outil] ERREUR: {self.error}"
        if self.events:
            combined = "\n".join(event.payload for event in self.events if event.payload)
            return f"[Outil stream]\n{combined}".strip()
        return "[Outil] Exécution en cours."

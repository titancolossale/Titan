# =====================================
# Titan Tool Execution Bridge
# =====================================

"""Bridge ThinkContext to ToolRuntime execution context (Phase 10A — P10A-025)."""

from __future__ import annotations

from core.execution_context import (
    ExecutionDispatchContext,
    build_tool_execution_context,
)
from brain.pipeline.context_bundle import ThinkContext

# Re-export for backward compatibility (Phase 12.8 — prefer core.execution_context).
__all__ = [
    "ExecutionDispatchContext",
    "build_tool_execution_context",
    "dispatch_context_from_think",
]


def dispatch_context_from_think(
    ctx: ThinkContext,
    *,
    conversation_session_id: str | None = None,
) -> ExecutionDispatchContext:
    """Build dispatch context from accumulated pipeline state."""
    session_id = ctx.session_id or conversation_session_id or "default"
    turn_id = ctx.turn_id or "default"
    return ExecutionDispatchContext(
        user=ctx.current_user,
        session_id=session_id,
        turn_id=turn_id,
        confirmed=ctx.tool_confirmed,
        confirmation_token=ctx.confirmation_token,
    )

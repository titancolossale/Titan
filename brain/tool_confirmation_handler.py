# =====================================
# Titan Tool Confirmation Handler
# =====================================

"""Parse user confirmation commands and resolve pending tool re-invocations (P10A-027)."""

from __future__ import annotations

import re

from brain.tool_execution_bridge import ExecutionDispatchContext
from tools.confirmation_gate import ConfirmationGate
from tools.tool_result import ToolRequest

_CONFIRM_PATTERN = re.compile(
    r"^(?:/confirm|confirme)\s+([0-9a-f-]{8,})\s*$",
    re.IGNORECASE,
)


def parse_confirmation_token(message: str) -> str | None:
    """Extract confirmation token from ``/confirm <token>`` or ``confirme <token>``."""
    match = _CONFIRM_PATTERN.match(message.strip())
    if match is None:
        return None
    return match.group(1)


def is_pure_confirmation_command(message: str) -> bool:
    """Return True when the message is solely a confirmation command."""
    return parse_confirmation_token(message) is not None


def resolve_confirmed_tool_requests(
    message: str,
    confirmation_gate: ConfirmationGate,
    *,
    session_id: str,
    user: str,
    turn_id: str,
) -> tuple[list[ToolRequest], ExecutionDispatchContext | None]:
    """Resolve pending tool invocations when the user confirms a prior request.

    Returns:
        Tuple of (tool requests to dispatch, confirmed dispatch context).
        Empty list and None when the message is not a confirmation command.
    """
    token = parse_confirmation_token(message)
    if token is None:
        return [], None

    pending = confirmation_gate.lookup_pending(token)
    if pending is None:
        return [], ExecutionDispatchContext(
            user=user,
            session_id=session_id,
            turn_id=turn_id,
            confirmed=True,
            confirmation_token=token,
        )

    if pending.session_id != session_id or pending.user != user:
        return [], ExecutionDispatchContext(
            user=user,
            session_id=session_id,
            turn_id=turn_id,
            confirmed=True,
            confirmation_token=token,
        )

    dispatch = ExecutionDispatchContext(
        user=user,
        session_id=session_id,
        turn_id=turn_id,
        confirmed=True,
        confirmation_token=token,
    )
    return [ToolRequest(pending.tool_name, dict(pending.params))], dispatch

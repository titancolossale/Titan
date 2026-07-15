# =====================================
# Titan Web Titan Service
# =====================================

"""Shared Titan Core instance for the web API — same composition root as the REPL."""

from __future__ import annotations

import logging

from typing import Any

from core.titan import Titan

logger = logging.getLogger(__name__)

_titan_instance: Titan | None = None


def get_titan() -> Titan:
    """Return the shared Titan instance, creating and marking it ONLINE on first use."""
    global _titan_instance
    if _titan_instance is None:
        _titan_instance = Titan()
        _titan_instance.status = "ONLINE"
        logger.info("Titan web service initialized (status=ONLINE)")
    return _titan_instance


def set_titan(titan: Titan | None) -> None:
    """Replace the shared Titan instance (tests only)."""
    global _titan_instance
    _titan_instance = titan


def reset_titan() -> None:
    """Clear the shared Titan instance (tests only)."""
    set_titan(None)


def _audit_start_index(titan: Titan) -> int:
    """Return current audit event count before a think() call."""
    tool_manager = getattr(titan, "tools", None)
    if tool_manager is None:
        return 0
    runtime = tool_manager.runtime
    if runtime is None or runtime.audit_logger is None:
        return 0
    return len(runtime.audit_logger.events())


def handle_chat(
    message: str,
    user: str | None = None,
    *,
    conversation_id: str | None = None,
    request_id: str | None = None,
    client_metadata: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Route a user message through Brain.process_request() with conversation tracking."""
    from api.chat_service import process_chat_message

    payload = process_chat_message(
        message,
        user=user,
        conversation_id=conversation_id,
        request_id=request_id,
        client_metadata=client_metadata,
    )
    return (
        payload["response"],
        payload["tool_activity"],
        payload["memory_activity"],
        payload["orchestrator_progress"],
        payload,
    )

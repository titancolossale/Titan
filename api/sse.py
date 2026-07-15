# =====================================
# Titan SSE Formatting
# =====================================

"""Server-Sent Events helpers for Titan web API — Phase E8."""

from __future__ import annotations

import json
from typing import Any

from api.event_hub import TitanStreamEvent


def format_sse_event(
    event_type: str,
    data: dict[str, Any],
    *,
    event_id: str | None = None,
) -> str:
    """Format a single SSE frame (event + data + optional id)."""
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    payload = json.dumps(data, ensure_ascii=False)
    lines.append(f"data: {payload}")
    lines.append("")
    return "\n".join(lines) + "\n"


def format_stream_event(event: TitanStreamEvent) -> str:
    """Format a ``TitanStreamEvent`` for SSE output."""
    return format_sse_event(event.event, event.data, event_id=event.id)


def sse_comment(text: str) -> str:
    """SSE comment line (keep-alive)."""
    return f": {text}\n\n"

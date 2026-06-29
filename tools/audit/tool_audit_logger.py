# =====================================
# Titan Tool Audit Logger
# =====================================

"""Append-only structured audit logging for tool executions (Phase 10A — P10A-023)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import TOOL_AUDIT_PATH
from tools.audit.tool_audit_models import ToolAuditEvent

logger = logging.getLogger("titan.tools.audit")


@dataclass
class ToolAuditLogger:
    """Write ToolAuditEvent records to JSONL and in-memory buffer."""

    file_path: Path | None = None
    enabled: bool = True
    _events: list[ToolAuditEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.file_path is None:
            self.file_path = TOOL_AUDIT_PATH

    def log(self, event: ToolAuditEvent) -> None:
        """Record an audit event in memory and append to JSONL when enabled."""
        self._events.append(event)
        if not self.enabled or self.file_path is None:
            return
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("Audit write failed: %s", exc)

    def events(self) -> list[ToolAuditEvent]:
        """Return all events recorded in this logger instance."""
        return list(self._events)

    def clear(self) -> None:
        """Clear in-memory events (tests only)."""
        self._events.clear()

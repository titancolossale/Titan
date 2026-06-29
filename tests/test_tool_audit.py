# =====================================
# Titan Tool Audit Tests
# =====================================

"""Unit tests for structured tool audit logging (Phase 10A — P10A-028)."""

from __future__ import annotations

import json
from pathlib import Path

from tools.audit.tool_audit_logger import ToolAuditLogger
from tools.audit.tool_audit_models import ToolAuditEvent, compute_params_digest


def test_params_digest_is_truncated_and_stable() -> None:
    """P10A-022: params digest never includes raw payload in audit."""
    digest = compute_params_digest({"query": "secret-value"})
    assert len(digest) == 16
    assert digest == compute_params_digest({"query": "secret-value"})


def test_audit_event_serializes_extended_fields() -> None:
    """P10A-022: audit events include runtime metadata fields."""
    event = ToolAuditEvent.build(
        event_type="completed",
        run_id="run-1",
        tool_name="time",
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        risk_level="safe",
        success=True,
        duration_ms=12.5,
        execution_mode="live",
        health_state="online",
        dependencies_checked=True,
    )
    data = event.to_dict()
    assert data["event_type"] == "completed"
    assert data["execution_mode"] == "live"
    assert data["dependencies_checked"] is True
    restored = ToolAuditEvent.from_dict(data)
    assert restored.run_id == "run-1"


def test_audit_logger_appends_jsonl(tmp_path: Path) -> None:
    """P10A-023: audit logger writes append-only JSONL."""
    audit_path = tmp_path / "tools_audit.jsonl"
    logger = ToolAuditLogger(file_path=audit_path, enabled=True)
    logger.log(
        ToolAuditEvent.build(
            event_type="invoked",
            run_id="run-1",
            tool_name="time",
            caller="brain",
        )
    )
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["tool_name"] == "time"
    assert logger.events()[0].event_type == "invoked"

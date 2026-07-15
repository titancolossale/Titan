# =====================================
# Titan Tool Activity Tests
# =====================================

"""Tests for Phase 17.7 tool activity formatting."""

from __future__ import annotations

from api.tool_activity import format_tool_activity, normalize_tool_key
from tools.audit.tool_audit_models import ToolAuditEvent


def _event(
    event_type: str,
    tool_name: str = "time",
    run_id: str = "run-1",
    success: bool | None = None,
) -> ToolAuditEvent:
    return ToolAuditEvent.build(
        event_type=event_type,
        tool_name=tool_name,
        run_id=run_id,
        success=success,
    )


def test_normalize_tool_key_maps_obsidian_to_notes() -> None:
    assert normalize_tool_key("obsidian_tool") == "obsidian"
    assert normalize_tool_key("vault_search") == "obsidian"


def test_format_tool_activity_returns_user_facing_records() -> None:
    events = [
        _event("started", tool_name="time", run_id="run-a"),
        _event("completed", tool_name="time", run_id="run-a", success=True),
    ]

    activity = format_tool_activity(events)

    assert len(activity) == 1
    record = activity[0]
    assert record["run_id"] == "run-a"
    assert record["tool"] == "time"
    assert record["title"] == "Horloge"
    assert record["icon"] == "◉"
    assert record["state"] == "complete"
    assert record["success"] is True
    assert "params_digest" not in record
    assert "event_type" not in record


def test_format_tool_activity_marks_failed_runs() -> None:
    events = [
        _event("started", tool_name="browser", run_id="run-b"),
        _event("failed", tool_name="browser", run_id="run-b", success=False),
    ]

    activity = format_tool_activity(events)

    assert activity[0]["state"] == "error"
    assert activity[0]["success"] is False
    assert activity[0]["steps"][-1] == "Interrompu."


def test_format_tool_activity_empty_input() -> None:
    assert format_tool_activity([]) == []

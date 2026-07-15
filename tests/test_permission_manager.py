# =====================================
# Titan Permission Manager Tests
# =====================================

"""Tests for Phase 12.6 Batch 1 — PermissionManager (P126-004)."""

from __future__ import annotations

import pytest

from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport
from tools.decision.obsidian_decision import ObsidianDecision
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_enums import RiskLevel


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


def _report(**kwargs: object) -> ToolDecisionReport:
    defaults = {
        "intent": Intent.FILE_READ,
        "confidence": 0.9,
        "tool_required": True,
        "candidate_tools": (),
        "selected_tool": "file_read",
        "decision_reason": "test",
        "risk_level": RiskLevel.LOW,
        "confirmation_required": False,
    }
    defaults.update(kwargs)
    return ToolDecisionReport(**defaults)


def test_auto_allowed_read_file(manager: PermissionManager) -> None:
    """P126-004: reading files is auto-allowed."""
    result = manager.evaluate("file_read", "read_file", {"path": "sample.txt"})
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_auto_allowed_search_notes(manager: PermissionManager) -> None:
    """P126-004: searching notes is auto-allowed."""
    result = manager.evaluate(
        "obsidian",
        "search_notes",
        {"action": "search_notes", "query": "titan"},
    )
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_auto_allowed_update_note(manager: PermissionManager) -> None:
    """P126-004: updating notes is auto-allowed."""
    result = manager.evaluate(
        "obsidian",
        "patch_note",
        {"action": "patch_note", "path": "notes/titan.md", "content": "update"},
    )
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_confirmation_required_delete_note(manager: PermissionManager) -> None:
    """P126-004: deleting notes requires confirmation."""
    result = manager.evaluate(
        "obsidian",
        "delete_note",
        {"action": "delete_note", "path": "notes/old.md"},
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED
    assert result.reason


def test_auto_allowed_browser_open_page(manager: PermissionManager) -> None:
    """Phase 13.1: opening a page is auto-allowed."""
    result = manager.evaluate(
        "browser",
        "open_page",
        {"action": "open_page", "url": "https://example.com"},
    )
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_confirmation_required_browser_click(manager: PermissionManager) -> None:
    """Phase 13.1: clicking buttons requires confirmation."""
    result = manager.evaluate(
        "browser",
        "click_button",
        {"action": "click_button"},
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_blocked_browser_execute_script(manager: PermissionManager) -> None:
    """Phase 13.1: script execution is blocked."""
    result = manager.evaluate(
        "browser",
        "execute_script",
        {"action": "execute_script"},
    )
    assert result.level == PermissionLevel.BLOCKED


def test_auto_allowed_calendar_list_events(manager: PermissionManager) -> None:
    """Phase 14.1: listing events is auto-allowed."""
    result = manager.evaluate("calendar", "list_events")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_confirmation_required_calendar_create_event(manager: PermissionManager) -> None:
    """Phase 14.1: creating events requires confirmation."""
    result = manager.evaluate("calendar", "create_event")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_blocked_calendar_share(manager: PermissionManager) -> None:
    """Phase 14.1: calendar sharing is blocked."""
    result = manager.evaluate("calendar", "share_calendar")
    assert result.level == PermissionLevel.BLOCKED


def test_confirmation_required_bulk_action(manager: PermissionManager) -> None:
    """P126-004: bulk changes require confirmation."""
    report = _report(affected_files=("a.py", "b.py", "c.py"))
    result = manager.evaluate(
        "file_write",
        "write_file",
        {"path": "a.py", "content": "x"},
        decision_report=report,
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_blocked_unsafe_filesystem_action(manager: PermissionManager) -> None:
    """P126-004: unknown filesystem actions outside allowed tools are blocked."""
    result = manager.evaluate(
        "file_read",
        "delete_file",
        {"action": "delete_file", "path": "sample.txt"},
    )
    assert result.level == PermissionLevel.BLOCKED


def test_blocked_unknown_tool(manager: PermissionManager) -> None:
    """P126-004: unregistered tools are blocked."""
    result = manager.evaluate("raw_shell", "execute", {"command": "rm -rf /"})
    assert result.level == PermissionLevel.BLOCKED


def test_create_note_auto_allowed_with_obsidian_decision(
    manager: PermissionManager,
) -> None:
    """P126-004: create_note auto-allowed when Obsidian decision approves."""
    report = _report(
        selected_tool="obsidian",
        obsidian_decision=ObsidianDecision.CREATE_NEW_NOTE.value,
    )
    result = manager.evaluate(
        "obsidian",
        "create_note",
        {"action": "create_note", "path": "projects/titan.md"},
        decision_report=report,
    )
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_create_note_confirmation_without_obsidian_decision(
    manager: PermissionManager,
) -> None:
    """P126-004: create_note without worthy decision requires confirmation."""
    result = manager.evaluate(
        "obsidian",
        "create_note",
        {"action": "create_note", "path": "notes/casual.md"},
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_confirmed_delete_becomes_auto_allowed(manager: PermissionManager) -> None:
    """P126-004: confirmed destructive actions proceed."""
    result = manager.evaluate(
        "obsidian",
        "delete_note",
        {"action": "delete_note", "path": "notes/old.md"},
        confirmed=True,
    )
    assert result.level == PermissionLevel.AUTO_ALLOWED

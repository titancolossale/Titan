# =====================================
# Titan Calendar Tool Tests
# =====================================

"""Tests for Phase 14.1 — Calendar connector foundation."""

from __future__ import annotations

import json

import pytest

from tools.calendar_tool import CalendarTool
from tools.connectors.calendar_backend import InMemoryCalendarBackend
from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.calendar_models import CalendarResult
from tools.connectors.calendar_permissions import evaluate_calendar_permission
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def backend() -> InMemoryCalendarBackend:
    store = InMemoryCalendarBackend()
    store.seed_defaults()
    return store


@pytest.fixture
def connector(backend: InMemoryCalendarBackend) -> CalendarConnector:
    return CalendarConnector(enabled=True, backend=backend)


@pytest.fixture
def calendar_tool(connector: CalendarConnector) -> CalendarTool:
    return CalendarTool(enabled=True, connector=connector)


def test_connector_list_calendars(connector: CalendarConnector) -> None:
    outcome = connector.execute("list_calendars", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["calendars"]
    assert "Calendrier principal" in payload["calendars"]


def test_connector_list_events(connector: CalendarConnector) -> None:
    outcome = connector.execute("list_events", {"calendar_id": "primary"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert len(payload["events"]) >= 1


def test_connector_search_events(connector: CalendarConnector) -> None:
    outcome = connector.execute("search_events", {"query": "Titan"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert any("Titan" in event["title"] for event in payload["events"])


def test_connector_detect_conflicts(connector: CalendarConnector) -> None:
    outcome = connector.execute(
        "detect_conflicts",
        {
            "calendar_id": "primary",
            "start_time": "2026-07-04T09:15:00",
            "end_time": "2026-07-04T09:45:00",
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "conflict"
    assert payload["conflicts"]


def test_connector_find_free_time(connector: CalendarConnector) -> None:
    outcome = connector.execute(
        "find_free_time",
        {
            "calendar_id": "primary",
            "start_time": "2026-07-04T08:00:00",
            "end_time": "2026-07-04T12:00:00",
            "duration_minutes": 30,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["free_slots"]


def test_connector_create_event_requires_confirmation(connector: CalendarConnector) -> None:
    outcome = connector.execute(
        "create_event",
        {
            "title": "Sync Titan",
            "start_time": "2026-07-05T10:00:00",
            "end_time": "2026-07-05T11:00:00",
        },
    )
    assert not outcome.success
    assert "confirmation" in outcome.error.lower()


def test_connector_create_event_with_confirmation(connector: CalendarConnector) -> None:
    outcome = connector.execute(
        "create_event",
        {
            "title": "Sync Titan",
            "start_time": "2026-07-05T10:00:00",
            "end_time": "2026-07-05T11:00:00",
            "confirmed": True,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "created"
    assert payload["title"] == "Sync Titan"


def test_connector_update_and_delete_event(connector: CalendarConnector) -> None:
    created = connector.execute(
        "create_event",
        {
            "title": "À modifier",
            "start_time": "2026-07-06T10:00:00",
            "end_time": "2026-07-06T11:00:00",
            "confirmed": True,
        },
    )
    event_id = json.loads(created.data)["event_id"]

    updated = connector.execute(
        "update_event",
        {
            "event_id": event_id,
            "title": "Modifié",
            "confirmed": True,
        },
    )
    assert updated.success
    assert json.loads(updated.data)["title"] == "Modifié"

    deleted = connector.execute(
        "delete_event",
        {"event_id": event_id, "confirmed": True},
    )
    assert deleted.success
    assert json.loads(deleted.data)["status"] == "deleted"


def test_connector_blocks_share_calendar(connector: CalendarConnector) -> None:
    outcome = connector.execute("share_calendar", {"calendar_id": "primary"})
    assert not outcome.success
    assert "bloquée" in outcome.error.lower()


def test_calendar_result_model_fields() -> None:
    result = CalendarResult(
        calendar_id="primary",
        event_id="evt-1",
        title="Réunion",
        description="Notes",
        start_time="2026-07-04T10:00:00",
        end_time="2026-07-04T11:00:00",
        attendees=("nolan@example.com",),
        location="Visio",
        status="ok",
        warnings=("mock",),
    )
    payload = json.loads(result.to_json())
    assert payload["calendar_id"] == "primary"
    assert payload["event_id"] == "evt-1"
    assert payload["attendees"] == ["nolan@example.com"]
    assert "mock" in payload["warnings"]


def test_permission_auto_allowed_list_events(manager: PermissionManager) -> None:
    result = manager.evaluate("calendar", "list_events")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_confirmation_create_event(manager: PermissionManager) -> None:
    result = manager.evaluate("calendar", "create_event")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_blocked_share_calendar(manager: PermissionManager) -> None:
    result = manager.evaluate("calendar", "share_calendar")
    assert result.level == PermissionLevel.BLOCKED


def test_calendar_tool_registered_in_tool_manager() -> None:
    manager = ToolManager()
    assert manager.registry.get("calendar") is not None
    schema = manager.registry.get("calendar").schema
    assert schema.name == "calendar"


def test_calendar_tool_run_list_events(calendar_tool: CalendarTool) -> None:
    result = calendar_tool.run(action="list_events")
    assert result.success
    assert result.source == "calendar"
    assert result.metadata["connector"] == "calendar"


def test_evaluate_calendar_permission_aliases() -> None:
    evaluation = evaluate_calendar_permission("list")
    assert evaluation.level.value == "auto_allowed"

# =====================================
# Titan Calendar CLI Tests
# =====================================

"""Tests for Calendar CLI commands (Phase 14.2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.calendar_cli import (
    dispatch_calendar_command,
    run_calendar_auth,
    run_calendar_health,
    run_calendar_list,
    run_calendar_smoke_test,
)
from tools.connectors.calendar_validator import CalendarValidationCode


def test_dispatch_calendar_health_command() -> None:
    with patch("core.calendar_cli.run_calendar_health", return_value=0) as mocked:
        assert dispatch_calendar_command("calendar-health") == 0
        mocked.assert_called_once()


def test_dispatch_unknown_command_returns_none() -> None:
    assert dispatch_calendar_command("unknown-command") is None


def test_run_calendar_health_success() -> None:
    validation = patch(
        "core.calendar_cli.validate_calendar_config",
        return_value=type(
            "Result",
            (),
            {
                "ok": True,
                "format_report": lambda self: "ok",
            },
        )(),
    )
    connector = patch(
        "core.calendar_cli.CalendarConnector",
        return_value=type(
            "Connector",
            (),
            {"health_check": lambda self: (True, "healthy")},
        )(),
    )
    with validation, connector:
        assert run_calendar_health() == 0


def test_run_calendar_health_validation_failure(capsys: pytest.CaptureFixture[str]) -> None:
    from tools.connectors.calendar_validator import CalendarValidationResult

    result = CalendarValidationResult(
        ok=False,
        code=CalendarValidationCode.CALENDAR_DISABLED,
        message="disabled",
    )
    with patch("core.calendar_cli.validate_calendar_config", return_value=result):
        exit_code = run_calendar_health()
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "disabled" in captured.out


def test_run_calendar_auth_success(capsys: pytest.CaptureFixture[str]) -> None:
    validation = patch(
        "core.calendar_cli.validate_calendar_config",
        return_value=type(
            "Result",
            (),
            {
                "ok": True,
                "format_report": lambda self: "ready",
            },
        )(),
    )
    oauth = patch(
        "core.calendar_cli.run_oauth_setup",
        return_value=(True, "Token saved"),
    )
    with validation, oauth:
        assert run_calendar_auth() == 0
    captured = capsys.readouterr()
    assert "Token saved" in captured.out


def test_run_calendar_list_success(capsys: pytest.CaptureFixture[str]) -> None:
    from tools.connectors.calendar_validator import CalendarValidationResult

    validation_result = CalendarValidationResult(
        ok=True,
        code=CalendarValidationCode.OK,
        message="ok",
        provider="mock",
    )
    connector_result = type(
        "Outcome",
        (),
        {
            "success": True,
            "data": '{"calendars": ["Principal", "Travail"]}',
        },
    )()
    with patch(
        "core.calendar_cli.validate_calendar_config",
        return_value=validation_result,
    ), patch(
        "core.calendar_cli.CalendarConnector",
        return_value=type(
            "Connector",
            (),
            {"execute": lambda self, action, params: connector_result},
        )(),
    ):
        assert run_calendar_list() == 0
    captured = capsys.readouterr()
    assert "Principal" in captured.out


def test_run_calendar_smoke_test_mock_provider(capsys: pytest.CaptureFixture[str]) -> None:
    from tools.connectors.calendar_validator import CalendarValidationResult

    validation_result = CalendarValidationResult(
        ok=True,
        code=CalendarValidationCode.OK,
        message="ok",
        provider="mock",
    )

    deleted_ids: set[str] = set()

    def fake_execute(self, action: str, params: dict):
        if action == "create_event" and not params.get("confirmed"):
            return type(
                "Outcome",
                (),
                {"success": False, "data": "", "error": "confirmation required"},
            )()
        if action == "update_event" and not params.get("confirmed"):
            return type(
                "Outcome",
                (),
                {"success": False, "data": "", "error": "confirmation required"},
            )()
        if action == "delete_event" and not params.get("confirmed"):
            return type(
                "Outcome",
                (),
                {"success": False, "data": "", "error": "confirmation required"},
            )()
        if action == "delete_event" and params.get("confirmed"):
            deleted_ids.add(str(params.get("event_id", "")))
            return type(
                "Outcome",
                (),
                {"success": True, "data": '{"status": "deleted"}'},
            )()
        if action == "read_event":
            event_id = str(params.get("event_id", ""))
            if event_id in deleted_ids:
                return type(
                    "Outcome",
                    (),
                    {"success": False, "data": "", "error": "not found"},
                )()
        payloads = {
            "list_calendars": '{"calendars": ["Principal"]}',
            "list_events": '{"events": []}',
            "search_events": '{"events": [{"event_id": "evt-1", "title": "Titan Calendar Validation Test (updated)"}]}',
            "detect_conflicts": '{"conflicts": []}',
            "find_free_time": '{"free_slots": [["2026-07-04T08:00:00","2026-07-04T08:30:00"]]}',
            "create_event": '{"event_id": "evt-1", "status": "created", "title": "Titan Calendar Validation Test"}',
            "read_event": '{"event_id": "evt-1", "title": "Titan Calendar Validation Test", "status": "ok"}',
            "update_event": '{"event_id": "evt-1", "title": "Titan Calendar Validation Test (updated)", "status": "updated"}',
        }
        return type(
            "Outcome",
            (),
            {"success": True, "data": payloads.get(action, "{}")},
        )()

    with patch(
        "core.calendar_cli.validate_calendar_config",
        return_value=validation_result,
    ), patch(
        "core.calendar_cli.CalendarConnector",
        return_value=type(
            "Connector",
            (),
            {"execute": fake_execute},
        )(),
    ):
        assert run_calendar_smoke_test() == 0
    captured = capsys.readouterr()
    assert "SUCCÈS" in captured.out

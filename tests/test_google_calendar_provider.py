# =====================================
# Titan Google Calendar Provider Tests
# =====================================

"""Tests for Phase 14.2 — Google Calendar backend with mocked API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.calendar_validator import (
    CalendarValidationCode,
    validate_calendar_config,
)
from tools.connectors.google_calendar_provider import GoogleCalendarProvider


@pytest.fixture
def mock_service() -> MagicMock:
    service = MagicMock()
    calendar_list = MagicMock()
    calendar_list.list.return_value.execute.return_value = {
        "items": [
            {"id": "primary", "summary": "Principal"},
            {"id": "work@example.com", "summary": "Travail"},
        ],
    }
    service.calendarList.return_value = calendar_list
    return service


@pytest.fixture
def google_provider(mock_service: MagicMock) -> GoogleCalendarProvider:
    return GoogleCalendarProvider(mock_service)


def test_google_list_calendars(google_provider: GoogleCalendarProvider) -> None:
    calendars = google_provider.list_calendars()
    assert len(calendars) == 2
    assert calendars[0].calendar_id == "primary"
    assert calendars[0].name == "Principal"


def test_google_list_events(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-1",
                "summary": "Réunion Titan",
                "description": "Phase 14",
                "start": {"dateTime": "2026-07-04T10:00:00Z"},
                "end": {"dateTime": "2026-07-04T11:00:00Z"},
                "location": "Visio",
                "attendees": [{"email": "nolan@example.com"}],
            },
        ],
    }
    mock_service.events.return_value = events_api

    events = google_provider.list_events(
        calendar_id="primary",
        start_time="2026-07-04T00:00:00Z",
        end_time="2026-07-05T00:00:00Z",
    )
    assert len(events) == 1
    assert events[0].event_id == "evt-1"
    assert events[0].title == "Réunion Titan"
    assert events[0].attendees == ["nolan@example.com"]


def test_google_read_event(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.get.return_value.execute.return_value = {
        "id": "evt-42",
        "summary": "Stand-up",
        "start": {"dateTime": "2026-07-04T09:00:00Z"},
        "end": {"dateTime": "2026-07-04T09:30:00Z"},
    }
    mock_service.events.return_value = events_api

    event = google_provider.read_event("evt-42")
    assert event is not None
    assert event.event_id == "evt-42"
    assert event.title == "Stand-up"


def test_google_search_events(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-search",
                "summary": "Titan planning",
                "start": {"dateTime": "2026-07-04T14:00:00Z"},
                "end": {"dateTime": "2026-07-04T15:00:00Z"},
            },
        ],
    }
    mock_service.events.return_value = events_api

    events = google_provider.search_events("Titan", calendar_id="primary")
    assert len(events) == 1
    assert "Titan" in events[0].title


def test_google_create_event(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.insert.return_value.execute.return_value = {
        "id": "evt-new",
        "summary": "Nouvelle réunion",
        "start": {"dateTime": "2026-07-05T10:00:00Z"},
        "end": {"dateTime": "2026-07-05T11:00:00Z"},
    }
    mock_service.events.return_value = events_api

    event = google_provider.create_event(
        calendar_id="primary",
        title="Nouvelle réunion",
        start_time="2026-07-05T10:00:00Z",
        end_time="2026-07-05T11:00:00Z",
    )
    assert event.event_id == "evt-new"
    events_api.insert.assert_called_once()


def test_google_update_event(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.get.return_value.execute.return_value = {
        "id": "evt-up",
        "summary": "Avant",
        "start": {"dateTime": "2026-07-05T10:00:00Z"},
        "end": {"dateTime": "2026-07-05T11:00:00Z"},
    }
    events_api.patch.return_value.execute.return_value = {
        "id": "evt-up",
        "summary": "Après",
        "start": {"dateTime": "2026-07-05T10:00:00Z"},
        "end": {"dateTime": "2026-07-05T11:00:00Z"},
    }
    mock_service.events.return_value = events_api

    event = google_provider.update_event("evt-up", title="Après")
    assert event.title == "Après"
    events_api.patch.assert_called_once()


def test_google_delete_event(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.get.return_value.execute.return_value = {
        "id": "evt-del",
        "summary": "À supprimer",
        "start": {"dateTime": "2026-07-05T10:00:00Z"},
        "end": {"dateTime": "2026-07-05T11:00:00Z"},
    }
    events_api.delete.return_value.execute.return_value = None
    mock_service.events.return_value = events_api

    deleted = google_provider.delete_event("evt-del")
    assert deleted is True
    events_api.delete.assert_called_once()


def test_google_detect_conflicts(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-busy",
                "summary": "Occupé",
                "start": {"dateTime": "2026-07-04T09:30:00Z"},
                "end": {"dateTime": "2026-07-04T10:30:00Z"},
            },
        ],
    }
    mock_service.events.return_value = events_api

    conflicts = google_provider.detect_conflicts(
        calendar_id="primary",
        start_time="2026-07-04T10:00:00Z",
        end_time="2026-07-04T11:00:00Z",
    )
    assert len(conflicts) == 1


def test_google_find_free_time(google_provider: GoogleCalendarProvider, mock_service: MagicMock) -> None:
    events_api = MagicMock()
    events_api.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-busy",
                "summary": "Occupé",
                "start": {"dateTime": "2026-07-04T10:00:00Z"},
                "end": {"dateTime": "2026-07-04T11:00:00Z"},
            },
        ],
    }
    mock_service.events.return_value = events_api

    slots = google_provider.find_free_time(
        calendar_id="primary",
        start_time="2026-07-04T08:00:00Z",
        end_time="2026-07-04T12:00:00Z",
        duration_minutes=30,
    )
    assert slots


def test_connector_with_google_backend(mock_service: MagicMock) -> None:
    provider = GoogleCalendarProvider(mock_service)
    connector = CalendarConnector(enabled=True, backend=provider)
    outcome = connector.execute("list_calendars", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["calendars"]
    assert payload["warnings"] == []


def test_validate_google_missing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_path = tmp_path / "client_secret.json"
    secret_path.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "secret"}}),
        encoding="utf-8",
    )
    token_path = tmp_path / "token.json"
    monkeypatch.setenv("TITAN_CALENDAR_PROVIDER", "google")
    monkeypatch.setenv("TITAN_GOOGLE_CALENDAR_ENABLED", "true")

    result = validate_calendar_config(
        enabled=True,
        timeout_seconds=30.0,
        provider="google",
        google_enabled=True,
        client_secret_path=secret_path,
        token_path=token_path,
    )
    assert not result.ok
    assert result.code == CalendarValidationCode.GOOGLE_MISSING_TOKEN


def test_validate_google_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_path = tmp_path / "client_secret.json"
    secret_path.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "secret"}}),
        encoding="utf-8",
    )
    token_path = tmp_path / "token.json"
    token_path.write_text('{"token": "x"}', encoding="utf-8")
    monkeypatch.setenv("TITAN_CALENDAR_PROVIDER", "google")
    monkeypatch.setenv("TITAN_GOOGLE_CALENDAR_ENABLED", "true")

    result = validate_calendar_config(
        enabled=True,
        timeout_seconds=30.0,
        provider="google",
        google_enabled=True,
        client_secret_path=secret_path,
        token_path=token_path,
    )
    assert result.ok
    assert result.provider == "google"


@patch("googleapiclient.discovery.build")
@patch("tools.connectors.google_calendar_provider.load_credentials")
def test_from_config_builds_service(
    mock_load_credentials: MagicMock,
    mock_build: MagicMock,
) -> None:
    mock_load_credentials.return_value = MagicMock(valid=True)
    mock_build.return_value = MagicMock()
    provider = GoogleCalendarProvider.from_config()
    assert provider.provider_name == "google"
    mock_build.assert_called_once()

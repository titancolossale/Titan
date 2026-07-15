# =====================================
# Titan Calendar Decision Tests
# =====================================

"""Tests for Calendar decision layer routing (Phase 14.1)."""

from __future__ import annotations

from tools.decision.calendar_decision import (
    CalendarDecision,
    CalendarDecisionEngine,
)
from tools.connectors.calendar_connector import CalendarConnector


def test_decision_list_events_french() -> None:
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Montre mon agenda demain",
    )
    assert result.decision == CalendarDecision.LIST_EVENTS
    assert result.tool_params_dict()["action"] == "list_events"


def test_decision_create_event_french() -> None:
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Ajoute une réunion au calendrier demain titre: Sprint review",
    )
    assert result.decision == CalendarDecision.CREATE_EVENT
    assert result.tool_params_dict()["action"] == "create_event"


def test_decision_search_events() -> None:
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Cherche dans mon calendrier Titan",
    )
    assert result.decision == CalendarDecision.SEARCH_EVENTS
    assert result.tool_params_dict()["action"] == "search_events"


def test_decision_list_tomorrow_french_nl() -> None:
    """Phase 14.4: natural-language tomorrow agenda query."""
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Titan, qu'est-ce que j'ai demain ?",
    )
    assert result.decision == CalendarDecision.LIST_EVENTS
    params = result.tool_params_dict()
    assert params["action"] == "list_events"
    assert "start_time" in params
    assert "end_time" in params


def test_decision_search_gym_events() -> None:
    """Phase 14.4: search events by related topic."""
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Titan, cherche mes événements liés au gym.",
    )
    assert result.decision == CalendarDecision.SEARCH_EVENTS
    assert result.tool_params_dict()["query"] == "gym"


def test_decision_find_free_time_demain() -> None:
    """Phase 14.4: relative-day free slot discovery."""
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Titan, trouve un créneau libre demain.",
    )
    assert result.decision == CalendarDecision.FIND_FREE_TIME
    params = result.tool_params_dict()
    assert params["action"] == "find_free_time"
    assert "09:00:00" in params["start_time"]


def test_connector_mock_fallback_is_configured() -> None:
    """Mock backend fallback must remain usable when Google OAuth is absent."""
    connector = CalendarConnector(enabled=True, provider="google")
    assert connector.backend.provider_name == "mock"
    assert connector.is_configured is True


# =====================================
# Titan Calendar Brain Flow Tests
# =====================================

"""End-to-end Brain routing tests for natural-language Calendar requests."""

from __future__ import annotations

import pytest

from brain.reasoning import Reasoning
from tools.decision.calendar_decision import CalendarDecision, CalendarDecisionEngine
from tools.decision.intent import Intent
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.connectors.calendar_connector import CalendarConnector


@pytest.fixture
def calendar_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.reasoning.TITAN_CALENDAR_ENABLED", True)


def test_brain_routes_list_events_french(calendar_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, montre mon agenda",
        available_tools=frozenset({"calendar"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "list_events"


def test_brain_routes_create_event(calendar_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Ajoute une réunion au calendrier demain",
        available_tools=frozenset({"calendar"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "create_event"


def test_intent_calendar_engine() -> None:
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Planifie une réunion demain dans mon calendrier",
        available_tools=frozenset({"calendar"}),
    )
    assert report.intent == Intent.CALENDAR


def test_decision_engine_search(calendar_env: None) -> None:
    connector = CalendarConnector(enabled=True)
    result = CalendarDecisionEngine(connector).decide(
        "Recherche dans mon calendrier la réunion Titan",
    )
    assert result.decision == CalendarDecision.SEARCH_EVENTS

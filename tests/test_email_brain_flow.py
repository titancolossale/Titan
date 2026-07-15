# =====================================
# Titan Email Brain Flow Tests
# =====================================

"""End-to-end Brain routing tests for natural-language Email requests."""

from __future__ import annotations

import pytest

from brain.reasoning import Reasoning
from tools.decision.email_decision import EmailDecision, EmailDecisionEngine
from tools.decision.intent import Intent
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.connectors.email_connector import EmailConnector


@pytest.fixture
def email_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.reasoning.TITAN_EMAIL_ENABLED", True)


def test_brain_routes_list_emails_french(email_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, montre mes emails",
        available_tools=frozenset({"email"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "list_emails"


def test_brain_routes_send_email(email_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Envoie un email à ibrahim@example.com",
        available_tools=frozenset({"email"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "send_email"


def test_intent_email_engine() -> None:
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Envoie un email à Ibrahim",
        available_tools=frozenset({"email"}),
    )
    assert report.intent == Intent.EMAIL
    assert report.selected_tool == "email"


def test_decision_engine_search(email_env: None) -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Recherche dans mes emails le message Titan",
    )
    assert result.decision == EmailDecision.SEARCH_EMAILS

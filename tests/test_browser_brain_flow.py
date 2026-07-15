# =====================================
# Titan Browser Brain Flow Tests
# =====================================

"""End-to-end Brain routing tests for natural-language Browser requests."""

from __future__ import annotations

import pytest

from brain.reasoning import Reasoning
from tools.decision.browser_decision import BrowserDecision, BrowserDecisionEngine
from tools.decision.intent import Intent
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.connectors.browser_connector import BrowserConnector


@pytest.fixture
def browser_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.reasoning.TITAN_BROWSER_ENABLED", True)


def test_brain_routes_open_page_french(browser_env: None) -> None:
    """« Titan, ouvre https://example.com » → open_page."""
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, ouvre https://example.com",
        available_tools=frozenset({"browser"}),
    )
    assert analysis["tool_requests"]
    params = analysis["tool_requests"][0].params
    assert params["action"] == "open_page"
    assert params["url"] == "https://example.com"


def test_brain_routes_read_current_page(browser_env: None) -> None:
    """« Titan, lis cette page » → read_page (session-aware, no URL)."""
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, lis cette page",
        available_tools=frozenset({"browser"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "read_page"
    assert "url" not in analysis["tool_requests"][0].params


def test_brain_routes_scroll_page(browser_env: None) -> None:
    """« Titan, fais défiler la page » → scroll_page."""
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Titan, fais défiler la page",
        available_tools=frozenset({"browser"}),
    )
    assert report.intent == Intent.BROWSER
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, fais défiler la page",
        available_tools=frozenset({"browser"}),
    )
    assert analysis["tool_requests"][0].params["action"] == "scroll_page"


def test_brain_routes_screenshot(browser_env: None) -> None:
    """« Titan, prends une capture d'écran » → take_screenshot."""
    connector = BrowserConnector(enabled=True)
    result = BrowserDecisionEngine(connector).decide(
        "Titan, prends une capture d'écran",
    )
    assert result.decision == BrowserDecision.TAKE_SCREENSHOT
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, prends une capture d'écran",
        available_tools=frozenset({"browser"}),
    )
    assert analysis["tool_requests"][0].params["action"] == "take_screenshot"

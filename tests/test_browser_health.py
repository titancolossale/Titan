# =====================================
# Titan Browser Health Tests
# =====================================

"""Health tests for Phase 13.1 — Browser connector registration and routing."""

from __future__ import annotations

from tools.connectors.browser_connector import BrowserConnector
from tools.decision.browser_decision import BrowserDecision, BrowserDecisionEngine
from tools.decision.intent import Intent
from tools.decision.intent_classifier import IntentClassifier
from tools.decision.tool_ranker import ToolRanker
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager


def test_browser_registered_in_tool_manager() -> None:
    manager = ToolManager()
    tool = manager.registry.get("browser")
    assert tool is not None
    assert tool.name == "browser"


def test_browser_intent_routing() -> None:
    classifier = IntentClassifier()
    classification = classifier.classify(
        "Ouvre la page https://example.com et lis le contenu",
    )
    assert classification.intent == Intent.BROWSER

    ranker = ToolRanker()
    candidates = ranker.rank(
        "Ouvre la page https://example.com",
        classification,
        available_tools=frozenset({"browser", "web_search"}),
    )
    assert candidates
    assert candidates[0].tool_name == "browser"


def test_browser_decision_engine_resolves_open_page() -> None:
    connector = BrowserConnector(enabled=True, fetcher=lambda url, timeout: ("", "", ()))
    engine = BrowserDecisionEngine(connector)
    result = engine.decide("Ouvre la page https://example.com/docs")
    assert result.decision == BrowserDecision.OPEN_PAGE
    assert result.tool_params_dict()["url"] == "https://example.com/docs"


def test_browser_permission_tiers() -> None:
    manager = PermissionManager()
    read_result = manager.evaluate(
        "browser",
        "open_page",
        {"action": "open_page", "url": "https://example.com"},
    )
    click_result = manager.evaluate("browser", "click_button", {"action": "click_button"})
    blocked_result = manager.evaluate("browser", "execute_script", {"action": "execute_script"})

    assert read_result.level == PermissionLevel.AUTO_ALLOWED
    assert click_result.level == PermissionLevel.CONFIRMATION_REQUIRED
    assert blocked_result.level == PermissionLevel.BLOCKED


def test_browser_session_starts() -> None:
    connector = BrowserConnector(
        enabled=True,
        fetcher=lambda url, timeout: ("<html></html>", "text/html", ()),
    )
    started, message = connector.start()
    assert started
    assert connector.session.started
    assert message

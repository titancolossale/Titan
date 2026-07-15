# =====================================
# Titan Trading Brain Flow Tests
# =====================================

"""End-to-end Brain routing tests for natural-language Trading requests."""

from __future__ import annotations

import pytest

from brain.reasoning import Reasoning
from tools.decision.intent import Intent
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.decision.trading_decision import TradingDecision, TradingDecisionEngine
from tools.connectors.trading_connector import TradingConnector


@pytest.fixture
def trading_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.reasoning.TITAN_TRADING_ENABLED", True)


def test_brain_routes_get_positions_french(trading_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Titan, montre mes positions NQ",
        available_tools=frozenset({"trading"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "get_positions"


def test_brain_routes_place_order(trading_env: None) -> None:
    reasoning = Reasoning()
    analysis = reasoning.analyze(
        "Place un ordre buy 1 NQ",
        available_tools=frozenset({"trading"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "place_order"


def test_intent_trading_engine() -> None:
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Buy 10 contracts of NQ",
        available_tools=frozenset({"trading"}),
    )
    assert report.intent == Intent.TRADING
    assert report.selected_tool == "trading"
    assert report.fallback_action.value == "execute_tool"


def test_decision_engine_get_price(trading_env: None) -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Quel est le prix du NQ sur le marché futures ?",
    )
    assert result.decision == TradingDecision.GET_PRICE

# =====================================
# Titan Trading Decision Tests
# =====================================

"""Tests for Trading decision layer routing (Phase 16.1)."""

from __future__ import annotations

from tools.decision.trading_decision import (
    TradingDecision,
    TradingDecisionEngine,
)
from tools.connectors.trading_connector import TradingConnector


def test_decision_get_positions_french() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Montre mes positions NQ",
    )
    assert result.decision == TradingDecision.GET_POSITIONS
    params = result.tool_params_dict()
    assert params["action"] == "get_positions"
    assert params["symbol"] == "NQ"


def test_decision_get_price() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Quel est le prix du NQ ?",
    )
    assert result.decision == TradingDecision.GET_PRICE
    params = result.tool_params_dict()
    assert params["action"] == "get_price"
    assert params["symbol"] == "NQ"


def test_decision_place_order_french() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Place un ordre buy 2 contrats NQ",
    )
    assert result.decision == TradingDecision.PLACE_ORDER
    params = result.tool_params_dict()
    assert params["action"] == "place_order"
    assert params["symbol"] == "NQ"
    assert params["side"] == "buy"
    assert params["quantity"] == 2.0


def test_decision_get_balance() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Quel est mon solde trading ?",
    )
    assert result.decision == TradingDecision.GET_BALANCE
    assert result.tool_params_dict()["action"] == "get_balance"


def test_decision_list_accounts() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Liste mes comptes trading",
    )
    assert result.decision == TradingDecision.LIST_ACCOUNTS
    assert result.tool_params_dict()["action"] == "list_accounts"


def test_decision_cancel_order() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Annule l'ordre ord-seed-001 sur mon compte futures",
    )
    assert result.decision == TradingDecision.CANCEL_ORDER
    assert result.tool_params_dict()["action"] == "cancel_order"


def test_decision_do_not_use_without_signal() -> None:
    connector = TradingConnector(enabled=True)
    result = TradingDecisionEngine(connector).decide(
        "Quelle heure est-il ?",
    )
    assert result.decision == TradingDecision.DO_NOT_USE_TRADING


def test_connector_mock_fallback_is_configured() -> None:
    """Mock provider fallback must remain usable when no broker is connected."""
    connector = TradingConnector(enabled=True, provider_name="mock")
    assert connector.is_configured

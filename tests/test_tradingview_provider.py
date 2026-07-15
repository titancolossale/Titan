# =====================================
# Titan TradingView Provider Tests
# =====================================

"""Tests for Phase 16.2 — TradingView webhook backend."""

from __future__ import annotations

import json

import pytest

from tools.connectors.trading_connector import TradingConnector
from tools.connectors.tradingview_models import AlertPayloadFormat, AlertValidationCode
from tools.connectors.tradingview_provider import TradingViewProvider
from tools.connectors.tradingview_webhook import handle_tradingview_webhook
from tools.decision.trading_decision import TradingDecision, TradingDecisionEngine
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.trading_tool import TradingTool


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "tradingview_alerts.json"


@pytest.fixture
def provider(store_path) -> TradingViewProvider:
    return TradingViewProvider(
        webhook_secret="test-secret",
        alert_store_path=store_path,
    )


@pytest.fixture
def connector(provider: TradingViewProvider) -> TradingConnector:
    return TradingConnector(enabled=True, provider=provider)


@pytest.fixture
def trading_tool(connector: TradingConnector) -> TradingTool:
    return TradingTool(enabled=True, connector=connector)


JSON_ALERT = {
    "strategy": "NQ Breakout",
    "symbol": "NQ1!",
    "market": "CME",
    "timeframe": "5m",
    "action": "buy",
    "contracts": 1,
    "price": 18450.25,
    "stop_loss": 18400.0,
    "take_profit": 18500.0,
}

PLAIN_ALERT = (
    "NQ Breakout: BUY NQ1! @ 18450.25 | SL: 18400 | TP: 18500 | 1 contract"
)

TITAN_ALERT = {
    "titan_version": "1",
    "payload_type": "titan_alert",
    "strategy_name": "ES Momentum",
    "symbol": "ES",
    "action": "sell",
    "contracts": 2,
    "price": 5200.5,
    "alert_id": "titan-alert-001",
}


def test_parse_json_alert(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(JSON_ALERT)
    assert parsed.format == AlertPayloadFormat.JSON
    assert parsed.fields["symbol"] == "NQ1!"
    assert parsed.fields["action"] == "buy"


def test_parse_plain_text_alert(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(PLAIN_ALERT)
    assert parsed.format == AlertPayloadFormat.PLAIN_TEXT
    assert parsed.strategy_hint == "NQ Breakout"
    assert parsed.fields["action"].lower() == "buy"
    assert parsed.fields["symbol"] == "NQ1!"


def test_parse_webhook_wrapper(provider: TradingViewProvider) -> None:
    payload = {"message": PLAIN_ALERT}
    parsed = provider.parse_alert(payload)
    assert parsed.format == AlertPayloadFormat.WEBHOOK
    assert "NQ Breakout" in parsed.strategy_hint


def test_parse_titan_custom_payload(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(TITAN_ALERT)
    assert parsed.format == AlertPayloadFormat.TITAN
    assert parsed.strategy_hint == "ES Momentum"
    assert parsed.fields["symbol"] == "ES"


def test_validate_alert_ok(provider: TradingViewProvider) -> None:
    result = provider.validate_alert(
        JSON_ALERT,
        secret="test-secret",
    )
    assert result.ok
    assert result.code == AlertValidationCode.OK


def test_validate_alert_invalid_secret(provider: TradingViewProvider) -> None:
    result = provider.validate_alert(JSON_ALERT, secret="wrong")
    assert not result.ok
    assert result.code == AlertValidationCode.INVALID_SECRET


def test_validate_alert_missing_symbol(store_path) -> None:
    provider = TradingViewProvider(webhook_secret="", alert_store_path=store_path)
    result = provider.validate_alert({"action": "buy"})
    assert not result.ok
    assert result.code == AlertValidationCode.MISSING_SYMBOL


def test_identify_strategy_from_plain_text(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(PLAIN_ALERT)
    assert provider.identify_strategy(parsed) == "NQ Breakout"


def test_identify_strategy_from_json(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(JSON_ALERT)
    assert provider.identify_strategy(parsed) == "NQ Breakout"


def test_extract_signal_json(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(JSON_ALERT)
    signal = provider.extract_signal(parsed)
    assert signal.strategy_name == "NQ Breakout"
    assert signal.symbol == "NQ"
    assert signal.action == "buy"
    assert signal.price == 18450.25
    assert signal.stop_loss == 18400.0
    assert signal.take_profit == 18500.0
    assert signal.timeframe == "5m"


def test_extract_signal_plain_text(provider: TradingViewProvider) -> None:
    parsed = provider.parse_alert(PLAIN_ALERT)
    signal = provider.extract_signal(parsed)
    assert signal.symbol == "NQ"
    assert signal.action == "buy"
    assert signal.price == 18450.25


def test_receive_alert_persists(provider: TradingViewProvider) -> None:
    signal = provider.receive_alert(JSON_ALERT, secret="test-secret")
    assert signal.alert_id
    stored = provider.get_latest_signal(symbol="NQ")
    assert stored is not None
    assert stored.strategy_name == "NQ Breakout"


def test_receive_alert_via_webhook_handler(provider: TradingViewProvider) -> None:
    body = json.dumps({**JSON_ALERT, "secret": "test-secret"})
    status, response = handle_tradingview_webhook(
        body,
        provider=provider,
        secret="test-secret",
    )
    assert status == 200
    assert response["ok"] is True
    assert response["signal"]["symbol"] == "NQ"


def test_webhook_handler_rejects_bad_secret(provider: TradingViewProvider) -> None:
    status, response = handle_tradingview_webhook(
        json.dumps(JSON_ALERT),
        provider=provider,
        secret="wrong",
    )
    assert status == 401
    assert response["ok"] is False


def test_connector_receive_alert(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "receive_alert",
        {"payload": JSON_ALERT, "webhook_secret": "test-secret"},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["signal"]["symbol"] == "NQ"


def test_connector_parse_alert(connector: TradingConnector) -> None:
    outcome = connector.execute("parse_alert", {"payload": PLAIN_ALERT})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["parsed_alert"]["format"] == "plain_text"


def test_connector_validate_alert(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "validate_alert",
        {"payload": JSON_ALERT, "webhook_secret": "test-secret"},
    )
    assert outcome.success


def test_connector_extract_signal(connector: TradingConnector) -> None:
    outcome = connector.execute("extract_signal", {"payload": JSON_ALERT})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["signal"]["action"] == "buy"


def test_connector_list_alerts(connector: TradingConnector) -> None:
    connector.execute(
        "receive_alert",
        {"payload": JSON_ALERT, "webhook_secret": "test-secret"},
    )
    outcome = connector.execute("list_alerts", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert len(payload["signals"]) >= 1


def test_connector_get_price_from_alert(connector: TradingConnector) -> None:
    connector.execute(
        "receive_alert",
        {"payload": JSON_ALERT, "webhook_secret": "test-secret"},
    )
    outcome = connector.execute("get_price", {"symbol": "NQ"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["last_price"] == 18450.25


def test_tradingview_provider_blocks_orders(provider: TradingViewProvider) -> None:
    with pytest.raises(ValueError, match="ne place pas"):
        provider.place_order("tradingview-alerts", symbol="NQ", side="buy", quantity=1)


def test_trading_tool_receive_alert(trading_tool: TradingTool) -> None:
    result = trading_tool.run(
        action="receive_alert",
        payload=json.dumps(JSON_ALERT),
        webhook_secret="test-secret",
    )
    assert result.success


def test_permission_manager_alert_actions_auto_allowed() -> None:
    manager = PermissionManager()
    for action in (
        "receive_alert",
        "parse_alert",
        "validate_alert",
        "identify_strategy",
        "extract_signal",
        "list_alerts",
        "get_latest_alert",
    ):
        outcome = manager.evaluate("trading", action)
        assert outcome.level == PermissionLevel.AUTO_ALLOWED, action


def test_decision_engine_routes_tradingview_list_alerts(
    connector: TradingConnector,
) -> None:
    engine = TradingDecisionEngine(connector=connector)
    result = engine.decide("Liste des alertes TradingView")
    assert result.decision == TradingDecision.LIST_ALERTS
    assert result.tool_params_dict()["action"] == "list_alerts"


def test_decision_engine_routes_latest_alert(connector: TradingConnector) -> None:
    engine = TradingDecisionEngine(connector=connector)
    result = engine.decide("Montre la dernière alerte TradingView pour NQ")
    assert result.decision == TradingDecision.GET_LATEST_ALERT


def test_decision_engine_routes_receive_alert(connector: TradingConnector) -> None:
    engine = TradingDecisionEngine(connector=connector)
    message = f"Reçois l'alerte TradingView {json.dumps(JSON_ALERT)}"
    result = engine.decide(message)
    assert result.decision == TradingDecision.RECEIVE_ALERT


def test_provider_factory_creates_tradingview() -> None:
    from tools.connectors.trading_provider_factory import create_trading_provider

    backend = create_trading_provider(provider="tradingview")
    assert backend.provider_name == "tradingview"

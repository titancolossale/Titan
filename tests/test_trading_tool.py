# =====================================
# Titan Trading Tool Tests
# =====================================

"""Tests for Phase 16.1 — Trading connector foundation."""

from __future__ import annotations

import json

import pytest

from tools.trading_tool import TradingTool
from tools.connectors.trading_connector import TradingConnector
from tools.connectors.trading_models import TradingResult
from tools.connectors.trading_permissions import evaluate_trading_permission
from tools.connectors.trading_provider import MockTradingProvider
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def provider() -> MockTradingProvider:
    store = MockTradingProvider()
    store.seed_defaults()
    return store


@pytest.fixture
def connector(provider: MockTradingProvider) -> TradingConnector:
    return TradingConnector(enabled=True, provider=provider)


@pytest.fixture
def trading_tool(connector: TradingConnector) -> TradingTool:
    return TradingTool(enabled=True, connector=connector)


def test_connector_list_accounts(connector: TradingConnector) -> None:
    outcome = connector.execute("list_accounts", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["accounts"]
    assert len(payload["accounts"]) >= 2


def test_connector_get_positions(connector: TradingConnector) -> None:
    outcome = connector.execute("get_positions", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["positions"]
    assert payload["positions"][0]["symbol"] == "NQ"


def test_connector_get_price(connector: TradingConnector) -> None:
    outcome = connector.execute("get_price", {"symbol": "NQ"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["symbol"] == "NQ"
    assert payload["last_price"] is not None
    assert payload["bid"] is not None
    assert payload["ask"] is not None


def test_connector_get_balance(connector: TradingConnector) -> None:
    outcome = connector.execute("get_balance", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["balance"] == 100_000.0
    assert payload["margin"] == 5_000.0


def test_connector_get_orders(connector: TradingConnector) -> None:
    outcome = connector.execute("get_orders", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["orders"]


def test_connector_get_market_status(connector: TradingConnector) -> None:
    outcome = connector.execute("get_market_status", {"market": "CME"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "open"


def test_connector_place_order_requires_confirmation(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "place_order",
        {"symbol": "NQ", "side": "buy", "quantity": 1},
    )
    assert not outcome.success
    assert "confirmation" in outcome.error.lower()


def test_connector_place_order_with_confirmation(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "place_order",
        {
            "symbol": "ES",
            "side": "buy",
            "quantity": 1,
            "confirmed": True,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["order_id"]
    assert payload["status"] == "filled"


def test_connector_cancel_order(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "cancel_order",
        {"order_id": "ord-seed-001", "confirmed": True},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "cancelled"


def test_connector_blocks_configure_provider(connector: TradingConnector) -> None:
    outcome = connector.execute("configure_provider", {"confirmed": True})
    assert not outcome.success
    assert "bloquée" in outcome.error.lower()


def test_connector_blocks_bulk_close_all(connector: TradingConnector) -> None:
    outcome = connector.execute(
        "bulk_close_all",
        {"bulk": True, "close_all": True, "confirmed": True},
    )
    assert not outcome.success
    assert "bloquée" in outcome.error.lower()


def test_trading_result_model_fields() -> None:
    result = TradingResult(
        provider="mock",
        account_name="Paper NQ — Nolan",
        account_id="paper-nq-001",
        market="CME",
        symbol="NQ",
        timeframe="1m",
        bid=18475.0,
        ask=18475.5,
        last_price=18475.25,
        pnl=125.5,
        balance=100_000.0,
        margin=5_000.0,
        status="ok",
        warnings=("mock",),
    )
    payload = json.loads(result.to_json())
    assert payload["provider"] == "mock"
    assert payload["account_name"] == "Paper NQ — Nolan"
    assert payload["account_id"] == "paper-nq-001"
    assert payload["market"] == "CME"
    assert payload["symbol"] == "NQ"
    assert payload["timeframe"] == "1m"
    assert payload["bid"] == 18475.0
    assert payload["ask"] == 18475.5
    assert payload["last_price"] == 18475.25
    assert payload["pnl"] == 125.5
    assert payload["balance"] == 100_000.0
    assert payload["margin"] == 5_000.0
    assert payload["status"] == "ok"
    assert "mock" in payload["warnings"]


def test_permission_auto_allowed_get_positions(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "get_positions")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_auto_allowed_get_price(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "get_price")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_confirmation_place_order(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "place_order")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_flatten_position(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "flatten_position")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_blocked_configure_provider(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "configure_provider")
    assert result.level == PermissionLevel.BLOCKED


def test_permission_blocked_reset_account(manager: PermissionManager) -> None:
    result = manager.evaluate("trading", "reset_account")
    assert result.level == PermissionLevel.BLOCKED


def test_trading_tool_registered_in_tool_manager() -> None:
    manager = ToolManager()
    assert manager.registry.get("trading") is not None
    schema = manager.registry.get("trading").schema
    assert schema.name == "trading"


def test_trading_tool_run_get_positions(trading_tool: TradingTool) -> None:
    result = trading_tool.run(action="get_positions")
    assert result.success
    assert result.source == "trading"
    assert result.metadata["connector"] == "trading"


def test_evaluate_trading_permission_aliases() -> None:
    evaluation = evaluate_trading_permission("positions")
    assert evaluation.level.value == "auto_allowed"

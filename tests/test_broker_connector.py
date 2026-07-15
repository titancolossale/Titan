# =====================================
# Titan Broker Connector Tests
# =====================================

"""Tests for Phase 16.3 — Broker Connector V1 (Paper Trading)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.connectors.broker_connector import BrokerConnector
from tools.connectors.broker_models import BrokerOrder
from tools.connectors.broker_provider_factory import create_broker_provider
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.signal_to_order import draft_order_from_signal
from tools.connectors.trading_connector import TradingConnector
from tools.connectors.trading_permissions import (
    TradingPermissionLevel,
    evaluate_trading_permission,
)
from tools.connectors.tradingview_models import TradingSignal


@pytest.fixture
def paper_provider() -> PaperBrokerProvider:
    provider = PaperBrokerProvider()
    provider.seed_defaults()
    return provider


@pytest.fixture
def broker(paper_provider: PaperBrokerProvider) -> BrokerConnector:
    return BrokerConnector(enabled=True, provider=paper_provider)


@pytest.fixture
def trading_connector(paper_provider: PaperBrokerProvider) -> TradingConnector:
    return TradingConnector(enabled=True, provider=paper_provider)


def test_paper_account_status(broker: BrokerConnector) -> None:
    outcome = broker.execute("account_status", {"account_id": "paper-nq-001"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["account_id"] == "paper-nq-001"
    assert payload["account_name"] == "Paper NQ — Nolan"
    assert payload["balance"] == 100_000.0
    assert payload["status"] == "active"


def test_paper_list_accounts(broker: BrokerConnector) -> None:
    outcome = broker.execute("list_accounts", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert len(payload["accounts"]) >= 2


def test_paper_order_creation_requires_confirmation(broker: BrokerConnector) -> None:
    outcome = broker.execute(
        "place_order",
        {"symbol": "ES", "side": "buy", "quantity": 1},
    )
    assert not outcome.success
    assert "confirmation" in outcome.error.lower()


def test_confirmed_paper_order_execution(broker: BrokerConnector) -> None:
    outcome = broker.execute(
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
    assert payload["order"]["status"] == "filled"
    assert payload["order"]["symbol"] == "ES"


def test_signal_to_order_conversion() -> None:
    signal = TradingSignal(
        strategy_name="NQ Breakout",
        symbol="NQ",
        market="CME",
        action="buy",
        contracts=2.0,
        price=18_500.0,
        stop_loss=18_450.0,
        take_profit=18_600.0,
        alert_id="alert-test-001",
    )
    draft = draft_order_from_signal(signal, account_id="paper-nq-001")
    assert draft.status == "draft"
    assert draft.order_id == ""
    assert draft.symbol == "NQ"
    assert draft.side == "buy"
    assert draft.quantity == 2.0
    assert draft.entry_price == 18_500.0
    assert draft.stop_loss == 18_450.0
    assert draft.take_profit == 18_600.0
    assert draft.source_signal_id == "alert-test-001"
    assert any("brouillon" in w.lower() for w in draft.warnings)


def test_draft_order_from_signal_via_connector(trading_connector: TradingConnector) -> None:
    outcome = trading_connector.execute(
        "draft_order_from_signal",
        {
            "symbol": "NQ",
            "action": "buy",
            "contracts": 1,
            "price": 18_500.0,
            "alert_id": "alert-002",
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["draft_order"]["status"] == "draft"
    assert payload["draft_order"]["symbol"] == "NQ"


def test_permission_blocking_without_confirmation() -> None:
    evaluation = evaluate_trading_permission("place_order")
    assert evaluation.level == TradingPermissionLevel.CONFIRMATION_REQUIRED
    evaluation = evaluate_trading_permission("modify_order")
    assert evaluation.level == TradingPermissionLevel.CONFIRMATION_REQUIRED
    evaluation = evaluate_trading_permission("cancel_order")
    assert evaluation.level == TradingPermissionLevel.CONFIRMATION_REQUIRED
    evaluation = evaluate_trading_permission("flatten_position")
    assert evaluation.level == TradingPermissionLevel.CONFIRMATION_REQUIRED


def test_cancel_order_paper_mode(broker: BrokerConnector) -> None:
    blocked = broker.execute("cancel_order", {"order_id": "ord-seed-001"})
    assert not blocked.success
    outcome = broker.execute(
        "cancel_order",
        {"order_id": "ord-seed-001", "confirmed": True},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "cancelled"


def test_modify_order_paper_mode(broker: BrokerConnector) -> None:
    outcome = broker.execute(
        "modify_order",
        {
            "order_id": "ord-seed-001",
            "quantity": 2,
            "entry_price": 18_520.0,
            "confirmed": True,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["order"]["quantity"] == 2.0
    assert payload["order"]["entry_price"] == 18_520.0


def test_flatten_position_paper_mode(broker: BrokerConnector) -> None:
    blocked = broker.execute("flatten_position", {"symbol": "NQ"})
    assert not blocked.success
    outcome = broker.execute(
        "flatten_position",
        {"symbol": "NQ", "confirmed": True},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["order"]["status"] == "filled"


def test_execute_signal_order_requires_confirmation(broker: BrokerConnector) -> None:
    outcome = broker.execute(
        "execute_signal_order",
        {
            "symbol": "ES",
            "action": "buy",
            "contracts": 1,
            "alert_id": "sig-001",
        },
    )
    assert not outcome.success
    assert "confirmation" in outcome.error.lower()


def test_execute_signal_order_confirmed(broker: BrokerConnector) -> None:
    outcome = broker.execute(
        "execute_signal_order",
        {
            "symbol": "ES",
            "action": "buy",
            "contracts": 1,
            "alert_id": "sig-002",
            "confirmed": True,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["order"]["source_signal_id"] == "sig-002"


def test_live_mode_blocked() -> None:
    with pytest.raises(ValueError, match="live"):
        create_broker_provider(mode="live", live_enabled=False)


def test_live_mode_blocked_even_when_flag_enabled() -> None:
    with pytest.raises(ValueError, match="Phase 16"):
        create_broker_provider(mode="live", live_enabled=True)


def test_apex_provider_blocked_without_read_only_flag() -> None:
    with pytest.raises(ValueError, match="TITAN_BROKER_READ_ONLY"):
        create_broker_provider(provider="apex", broker_read_only=False)


def test_apex_provider_read_only_stub() -> None:
    provider = create_broker_provider(provider="apex", broker_read_only=True)
    assert provider.provider_name == "apex"
    assert provider.execution_supported is False


def test_rithmic_provider_read_only_stub() -> None:
    provider = create_broker_provider(provider="rithmic", broker_read_only=True)
    assert provider.provider_name == "rithmic"
    assert provider.read_only_supported is True


def test_ninjatrader_provider_read_only_stub() -> None:
    provider = create_broker_provider(provider="ninjatrader", broker_read_only=True)
    assert provider.provider_name == "ninjatrader"


def test_tradovate_provider_read_only_stub() -> None:
    provider = create_broker_provider(provider="tradovate", broker_read_only=True)
    assert provider.provider_name == "tradovate"


def test_no_live_broker_sdk_imports_in_connectors() -> None:
    """Ensure no live Apex/Rithmic/NinjaTrader SDK imports landed in connectors."""
    connectors_dir = Path(__file__).resolve().parents[1] / "tools" / "connectors"
    forbidden = ("apex", "rithmic", "ninjatrader", "tradovate")
    sdk_patterns = (
        "import apex",
        "from apex",
        "import rithmic",
        "from rithmic",
        "import tradovate",
        "from tradovate",
        "import ninjatrader",
        "from ninjatrader",
    )
    for path in connectors_dir.glob("*.py"):
        name = path.name.lower()
        text = path.read_text(encoding="utf-8").lower()
        if "broker" not in name:
            continue
        for pattern in sdk_patterns:
            assert pattern not in text, f"Forbidden SDK import in {path.name}: {pattern}"


def test_broker_order_model_fields() -> None:
    order = BrokerOrder(
        order_id="ord-test",
        account_id="paper-nq-001",
        symbol="NQ",
        market="CME",
        side="buy",
        order_type="limit",
        quantity=1.0,
        entry_price=18_500.0,
        stop_loss=18_450.0,
        take_profit=18_600.0,
        status="working",
        source_signal_id="alert-xyz",
        warnings=("paper",),
    )
    payload = json.loads(order.to_json())
    assert payload["order_id"] == "ord-test"
    assert payload["account_id"] == "paper-nq-001"
    assert payload["entry_price"] == 18_500.0
    assert payload["stop_loss"] == 18_450.0
    assert payload["take_profit"] == 18_600.0
    assert payload["source_signal_id"] == "alert-xyz"
    assert payload["warnings"] == ["paper"]

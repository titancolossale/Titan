# =====================================
# Titan Broker Read-Only Tests
# =====================================

"""Tests for Phase 16.4 — Broker Provider Read-Only Foundation."""

from __future__ import annotations

import json

import pytest

from config.settings import TITAN_BROKER_READ_ONLY
from tools.connectors.broker_connector import BrokerConnector
from tools.connectors.broker_provider_factory import create_broker_provider
from tools.connectors.broker_readiness import (
    active_provider_readiness,
    collect_broker_readiness_reports,
    format_broker_health_report,
    is_read_only_provider,
    trading_safety_snapshot,
)
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.read_only_broker_provider import BrokerWriteBlockedError
from tools.connectors.real_broker_stubs import create_real_broker_stub


@pytest.fixture
def paper_provider() -> PaperBrokerProvider:
    provider = PaperBrokerProvider()
    provider.seed_defaults()
    return provider


@pytest.fixture
def paper_broker(paper_provider: PaperBrokerProvider) -> BrokerConnector:
    return BrokerConnector(enabled=True, provider=paper_provider)


@pytest.fixture
def apex_stub_broker() -> BrokerConnector:
    provider = create_real_broker_stub("apex")
    return BrokerConnector(enabled=True, provider=provider)


def test_trading_safety_defaults() -> None:
    safety = trading_safety_snapshot(
        mode="paper",
        live_enabled=False,
        broker_read_only=True,
    )
    assert safety["paper_mode_active"] is True
    assert safety["live_trading_enabled"] is False
    assert safety["broker_read_only"] is True
    assert safety["live_execution_allowed"] is False


def test_read_only_provider_flags() -> None:
    paper = PaperBrokerProvider()
    apex = create_real_broker_stub("apex")
    assert is_read_only_provider(paper) is False
    assert is_read_only_provider(apex) is True
    assert paper.execution_supported is True
    assert apex.execution_supported is False


def test_write_operations_blocked_on_read_only_provider(
    apex_stub_broker: BrokerConnector,
) -> None:
    for action, params in (
        ("place_order", {"symbol": "NQ", "side": "buy", "quantity": 1, "confirmed": True}),
        ("modify_order", {"order_id": "ord-1", "confirmed": True}),
        ("cancel_order", {"order_id": "ord-1", "confirmed": True}),
        ("flatten_position", {"symbol": "NQ", "confirmed": True}),
        ("execute_signal_order", {"symbol": "NQ", "action": "buy", "contracts": 1, "confirmed": True}),
    ):
        outcome = apex_stub_broker.execute(action, params)
        assert not outcome.success, action
        assert "lecture seule" in outcome.error.lower()


def test_write_blocked_at_provider_layer_even_if_bypassed() -> None:
    provider = create_real_broker_stub("rithmic")
    with pytest.raises(BrokerWriteBlockedError, match="place_order"):
        provider.place_order("acct", symbol="NQ", side="buy", quantity=1)
    with pytest.raises(BrokerWriteBlockedError, match="modify_order"):
        provider.modify_order("ord-1")
    with pytest.raises(BrokerWriteBlockedError, match="cancel_order"):
        provider.cancel_order("ord-1")
    with pytest.raises(BrokerWriteBlockedError, match="flatten_position"):
        provider.flatten_position("acct", symbol="NQ")


def test_live_trading_disabled_in_factory() -> None:
    with pytest.raises(ValueError, match="live"):
        create_broker_provider(mode="live", live_enabled=False)
    with pytest.raises(ValueError, match="Phase 16"):
        create_broker_provider(mode="live", live_enabled=True)


def test_real_provider_requires_read_only_flag() -> None:
    with pytest.raises(ValueError, match="TITAN_BROKER_READ_ONLY"):
        create_broker_provider(provider="apex", broker_read_only=False)


def test_real_provider_stub_when_read_only_enabled() -> None:
    provider = create_broker_provider(provider="apex", broker_read_only=True)
    assert provider.provider_name == "apex"
    assert provider.read_only_supported is True
    assert provider.execution_supported is False


def test_provider_readiness_report_fields() -> None:
    reports = collect_broker_readiness_reports()
    names = {report.provider_name for report in reports}
    assert "paper" in names
    assert "apex" in names
    assert "rithmic" in names
    assert "tradovate" in names
    assert "ninjatrader" in names

    apex = next(report for report in reports if report.provider_name == "apex")
    assert apex.read_only_supported is True
    assert apex.execution_supported is False
    assert apex.credentials_present is False
    assert apex.status == "credentials_missing"


def test_active_provider_readiness_paper() -> None:
    report = active_provider_readiness(provider="paper", broker_read_only=True)
    assert report.provider_name == "paper"
    assert report.execution_supported is True
    assert report.read_only_supported is False
    assert report.status == "ready"


def test_broker_health_report_contains_safety_flags() -> None:
    report = format_broker_health_report(
        provider="paper",
        mode="paper",
        live_enabled=False,
        broker_read_only=True,
    )
    assert "TITAN_BROKER_READ_ONLY" in report
    assert "TITAN_TRADING_LIVE_ENABLED" in report
    assert "TITAN_TRADING_MODE" in report
    assert "place_order" in report


def test_paper_get_pnl_and_margin(paper_broker: BrokerConnector) -> None:
    pnl_outcome = paper_broker.execute("get_pnl", {"account_id": "paper-nq-001"})
    assert pnl_outcome.success
    pnl_payload = json.loads(pnl_outcome.data)
    assert pnl_payload["pnl"]["account_id"] == "paper-nq-001"
    assert pnl_payload["pnl"]["unrealized_pnl"] == 125.50

    margin_outcome = paper_broker.execute("get_margin", {"account_id": "paper-nq-001"})
    assert margin_outcome.success
    margin_payload = json.loads(margin_outcome.data)
    assert margin_payload["margin"] == 5_000.0


def test_no_real_order_execution_path_for_real_provider(
    apex_stub_broker: BrokerConnector,
) -> None:
    read_outcome = apex_stub_broker.execute("list_accounts", {})
    assert not read_outcome.success
    assert "list_accounts" in read_outcome.error.lower() or "identifiants" in read_outcome.error.lower()

    write_outcome = apex_stub_broker.execute(
        "place_order",
        {"symbol": "NQ", "side": "buy", "quantity": 1, "confirmed": True},
    )
    assert not write_outcome.success
    assert "lecture seule" in write_outcome.error.lower()


def test_default_broker_read_only_setting_enabled() -> None:
    assert TITAN_BROKER_READ_ONLY is True

# =====================================
# Titan Apex/Rithmic Provider Tests
# =====================================

"""Tests for Phase 16.5 — Apex/Rithmic Read-Only Adapter Foundation."""

from __future__ import annotations

import pytest

from tools.connectors.apex_rithmic_provider import (
    APEX_RITHMIC_PROVIDER_KEY,
    ApexRithmicProvider,
    apex_rithmic_credentials_present,
    build_apex_rithmic_readiness_report,
    collect_apex_rithmic_credential_status,
    create_apex_rithmic_provider,
)
from tools.connectors.broker_connector import BrokerConnector
from tools.connectors.broker_provider_factory import create_broker_provider
from tools.connectors.broker_readiness import (
    active_provider_readiness,
    apex_rithmic_broker_readiness,
    collect_broker_readiness_reports,
    format_broker_health_report,
    is_read_only_provider,
)
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.read_only_broker_provider import BrokerWriteBlockedError


@pytest.fixture
def apex_rithmic_broker() -> BrokerConnector:
    provider = create_apex_rithmic_provider(
        rithmic_enabled=True,
        broker_read_only=True,
        live_enabled=False,
    )
    return BrokerConnector(enabled=True, provider=provider)


def test_apex_rithmic_provider_registration_via_factory() -> None:
    provider = create_broker_provider(
        provider="apex_rithmic",
        broker_read_only=True,
    )
    assert isinstance(provider, ApexRithmicProvider)
    assert provider.provider_name == APEX_RITHMIC_PROVIDER_KEY
    assert provider.read_only_supported is True
    assert provider.execution_supported is False


def test_apex_rithmic_provider_requires_read_only_flag() -> None:
    with pytest.raises(ValueError, match="TITAN_BROKER_READ_ONLY"):
        create_broker_provider(provider="apex_rithmic", broker_read_only=False)


def test_apex_rithmic_provider_disabled_by_default() -> None:
    report = build_apex_rithmic_readiness_report(rithmic_enabled=False)
    assert report.status == "provider_disabled"
    assert report.configured is False
    assert report.execution_supported is False
    assert any("TITAN_RITHMIC_ENABLED=false" in warning for warning in report.warnings)


def test_apex_rithmic_missing_credentials_when_enabled() -> None:
    report = build_apex_rithmic_readiness_report(
        rithmic_enabled=True,
        broker_read_only=True,
    )
    assert report.status == "credentials_missing"
    assert report.credentials_present is False
    assert report.configured is False
    assert any("Identifiants manquants" in warning for warning in report.warnings)


def test_apex_rithmic_credentials_present_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_RITHMIC_USERNAME", "test-user")
    monkeypatch.setenv("TITAN_RITHMIC_PASSWORD", "test-pass")
    report = build_apex_rithmic_readiness_report(
        rithmic_enabled=True,
        broker_read_only=True,
        live_enabled=False,
    )
    assert report.status == "scaffold_ready"
    assert report.credentials_present is True
    assert report.configured is True
    assert report.read_only_supported is True
    assert report.execution_supported is False
    assert any("lecture seule actif" in warning for warning in report.warnings)
    assert any("Exécution désactivée" in warning for warning in report.warnings)


def test_apex_rithmic_credential_status_flags() -> None:
    status = collect_apex_rithmic_credential_status(
        rithmic_enabled=False,
        broker_read_only=True,
        live_enabled=False,
    )
    assert status.provider_enabled is False
    assert status.read_only_active is True
    assert status.execution_disabled is True


def test_apex_rithmic_read_only_provider_flag() -> None:
    provider = create_apex_rithmic_provider(broker_read_only=True)
    assert is_read_only_provider(provider) is True
    assert is_read_only_provider(PaperBrokerProvider()) is False


def test_apex_rithmic_write_operations_blocked_at_provider_layer() -> None:
    provider = create_apex_rithmic_provider(
        rithmic_enabled=True,
        broker_read_only=True,
    )
    for method_name, call in (
        ("place_order", lambda: provider.place_order("acct", symbol="NQ", side="buy", quantity=1)),
        ("modify_order", lambda: provider.modify_order("ord-1")),
        ("cancel_order", lambda: provider.cancel_order("ord-1")),
        ("flatten_position", lambda: provider.flatten_position("acct", symbol="NQ")),
    ):
        with pytest.raises(BrokerWriteBlockedError, match=method_name):
            call()


def test_apex_rithmic_write_operations_blocked_via_connector_even_confirmed(
    apex_rithmic_broker: BrokerConnector,
) -> None:
    for action, params in (
        ("place_order", {"symbol": "NQ", "side": "buy", "quantity": 1, "confirmed": True}),
        ("modify_order", {"order_id": "ord-1", "confirmed": True}),
        ("cancel_order", {"order_id": "ord-1", "confirmed": True}),
        ("flatten_position", {"symbol": "NQ", "confirmed": True}),
        ("execute_signal_order", {"symbol": "NQ", "action": "buy", "contracts": 1, "confirmed": True}),
    ):
        outcome = apex_rithmic_broker.execute(action, params)
        assert not outcome.success, action
        assert "lecture seule" in outcome.error.lower() or "bloqué" in outcome.error.lower()


def test_apex_rithmic_no_live_execution_path(
    apex_rithmic_broker: BrokerConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TITAN_RITHMIC_USERNAME", "test-user")
    monkeypatch.setenv("TITAN_RITHMIC_PASSWORD", "test-pass")
    provider = create_apex_rithmic_provider(
        rithmic_enabled=True,
        broker_read_only=True,
        live_enabled=False,
    )
    broker = BrokerConnector(enabled=True, provider=provider)

    read_outcome = broker.execute("list_accounts", {})
    assert not read_outcome.success
    assert "scaffold" in read_outcome.error.lower() or "sdk" in read_outcome.error.lower()

    write_outcome = broker.execute(
        "place_order",
        {"symbol": "NQ", "side": "buy", "quantity": 1, "confirmed": True},
    )
    assert not write_outcome.success
    assert "lecture seule" in write_outcome.error.lower() or "bloqué" in write_outcome.error.lower()


def test_apex_rithmic_read_unavailable_when_disabled() -> None:
    provider = create_apex_rithmic_provider(rithmic_enabled=False)
    with pytest.raises(ValueError, match="désactivé"):
        provider.list_accounts()


def test_apex_rithmic_collect_readiness_in_reports() -> None:
    reports = collect_broker_readiness_reports()
    names = {report.provider_name for report in reports}
    assert APEX_RITHMIC_PROVIDER_KEY in names


def test_apex_rithmic_active_provider_readiness() -> None:
    report = active_provider_readiness(
        provider=APEX_RITHMIC_PROVIDER_KEY,
        broker_read_only=True,
    )
    assert report.provider_name == APEX_RITHMIC_PROVIDER_KEY
    assert report.execution_supported is False


def test_apex_rithmic_broker_health_report() -> None:
    report = format_broker_health_report(
        provider=APEX_RITHMIC_PROVIDER_KEY,
        mode="paper",
        live_enabled=False,
        broker_read_only=True,
    )
    assert "TITAN_RITHMIC_ENABLED" in report
    assert "TITAN_BROKER_PROVIDER" in report
    assert "apex_rithmic" in report
    assert "place_order" in report


def test_apex_rithmic_credentials_present_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    assert apex_rithmic_credentials_present() is False
    monkeypatch.setenv("TITAN_RITHMIC_USERNAME", "user")
    assert apex_rithmic_credentials_present() is False
    monkeypatch.setenv("TITAN_RITHMIC_PASSWORD", "pass")
    assert apex_rithmic_credentials_present() is True


def test_apex_rithmic_broker_readiness_wrapper() -> None:
    report = apex_rithmic_broker_readiness(rithmic_enabled=False)
    assert report.provider_name == APEX_RITHMIC_PROVIDER_KEY
    assert report.status == "provider_disabled"


def test_no_rithmic_sdk_imports_in_apex_rithmic_provider() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / "connectors" / "apex_rithmic_provider.py"
    text = path.read_text(encoding="utf-8").lower()
    forbidden = (
        "import rithmic",
        "from rithmic",
        "import apex",
        "from apex",
    )
    for pattern in forbidden:
        assert pattern not in text, f"Forbidden SDK import pattern: {pattern}"

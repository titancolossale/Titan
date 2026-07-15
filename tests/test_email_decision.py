# =====================================
# Titan Email Decision Tests
# =====================================

"""Tests for Email decision layer routing (Phase 15.1)."""

from __future__ import annotations

from tools.decision.email_decision import (
    EmailDecision,
    EmailDecisionEngine,
)
from tools.connectors.email_connector import EmailConnector


def test_decision_list_emails_french() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Montre mes emails",
    )
    assert result.decision == EmailDecision.LIST_EMAILS
    assert result.tool_params_dict()["action"] == "list_emails"


def test_decision_search_emails() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Cherche dans mes emails Titan",
    )
    assert result.decision == EmailDecision.SEARCH_EMAILS
    assert result.tool_params_dict()["action"] == "search_emails"


def test_decision_send_email_french() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Envoie un email à ibrahim@example.com",
    )
    assert result.decision == EmailDecision.SEND_EMAIL
    params = result.tool_params_dict()
    assert params["action"] == "send_email"
    assert params["recipients"] == "ibrahim@example.com"


def test_decision_compose_email() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Rédige un email à ibrahim@example.com objet: Phase 15",
    )
    assert result.decision == EmailDecision.COMPOSE_EMAIL
    params = result.tool_params_dict()
    assert params["action"] == "compose_email"
    assert params["recipients"] == "ibrahim@example.com"


def test_decision_delete_email() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Supprime cet email de ma boîte",
    )
    assert result.decision == EmailDecision.DELETE_EMAIL
    assert result.tool_params_dict()["action"] == "delete_email"


def test_decision_do_not_use_without_signal() -> None:
    connector = EmailConnector(enabled=True)
    result = EmailDecisionEngine(connector).decide(
        "Quelle heure est-il ?",
    )
    assert result.decision == EmailDecision.DO_NOT_USE_EMAIL


def test_connector_mock_fallback_is_configured() -> None:
    """Mock backend fallback must remain usable when Gmail is not connected."""
    connector = EmailConnector(enabled=True, provider="gmail")
    assert connector.is_configured

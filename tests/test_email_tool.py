# =====================================
# Titan Email Tool Tests
# =====================================

"""Tests for Phase 15.1 — Email connector foundation."""

from __future__ import annotations

import json

import pytest

from tools.email_tool import EmailTool
from tools.connectors.email_backend import InMemoryEmailBackend
from tools.connectors.email_connector import EmailConnector
from tools.connectors.email_models import EmailResult
from tools.connectors.email_permissions import evaluate_email_permission
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def backend() -> InMemoryEmailBackend:
    store = InMemoryEmailBackend()
    store.seed_defaults()
    return store


@pytest.fixture
def connector(backend: InMemoryEmailBackend) -> EmailConnector:
    return EmailConnector(enabled=True, backend=backend)


@pytest.fixture
def email_tool(connector: EmailConnector) -> EmailTool:
    return EmailTool(enabled=True, connector=connector)


def test_connector_list_emails(connector: EmailConnector) -> None:
    outcome = connector.execute("list_emails", {})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["emails"]
    assert len(payload["emails"]) >= 2


def test_connector_search_emails(connector: EmailConnector) -> None:
    outcome = connector.execute("search_emails", {"query": "Titan"})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert any("Titan" in email["subject"] for email in payload["emails"])


def test_connector_read_email(connector: EmailConnector, backend: InMemoryEmailBackend) -> None:
    message_id = next(iter(backend._emails))
    outcome = connector.execute("read_email", {"message_id": message_id})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["message_id"] == message_id
    assert payload["sender"]
    assert payload["subject"]


def test_connector_compose_requires_confirmation(connector: EmailConnector) -> None:
    outcome = connector.execute(
        "compose_email",
        {
            "recipients": ["ibrahim@example.com"],
            "subject": "Test",
            "body": "Hello",
        },
    )
    assert not outcome.success
    assert "confirmation" in outcome.error.lower()


def test_connector_compose_with_confirmation(connector: EmailConnector) -> None:
    outcome = connector.execute(
        "compose_email",
        {
            "recipients": ["ibrahim@example.com"],
            "subject": "Test",
            "body": "Hello",
            "confirmed": True,
        },
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["status"] == "draft"
    assert payload["draft_id"]


def test_connector_send_email_not_available_on_mock_backend(
    connector: EmailConnector,
) -> None:
    without = connector.execute(
        "send_email",
        {"recipients": ["ibrahim@example.com"], "subject": "Hi"},
    )
    assert not without.success
    assert "confirmation" in without.error.lower()

    with_confirmed = connector.execute(
        "send_email",
        {
            "recipients": ["ibrahim@example.com"],
            "subject": "Hi",
            "confirmed": True,
        },
    )
    assert not with_confirmed.success
    assert "mock" in with_confirmed.error.lower()


def test_connector_archive_and_mark_read(connector: EmailConnector, backend: InMemoryEmailBackend) -> None:
    message_id = next(iter(backend._emails))
    archived = connector.execute(
        "archive_email",
        {"message_id": message_id, "confirmed": True},
    )
    assert archived.success
    assert json.loads(archived.data)["status"] == "archived"

    marked = connector.execute(
        "mark_read",
        {"message_id": message_id, "confirmed": True},
    )
    assert marked.success
    assert json.loads(marked.data)["unread"] is False


def test_connector_blocks_bulk_delete(connector: EmailConnector) -> None:
    outcome = connector.execute(
        "bulk_delete",
        {"message_ids": ["a", "b"], "confirmed": True},
    )
    assert not outcome.success
    assert "bloquée" in outcome.error.lower()


def test_email_result_model_fields() -> None:
    result = EmailResult(
        message_id="msg-abc",
        sender="nolan@example.com",
        recipients=("ibrahim@example.com",),
        subject="Phase 15",
        preview="Preview text",
        body="Full body",
        attachments=("doc.pdf",),
        labels=("inbox", "work"),
        unread=True,
        received_time="2026-07-04T10:00:00",
        status="ok",
        warnings=("mock",),
    )
    payload = json.loads(result.to_json())
    assert payload["message_id"] == "msg-abc"
    assert payload["sender"] == "nolan@example.com"
    assert payload["recipients"] == ["ibrahim@example.com"]
    assert payload["attachments"] == ["doc.pdf"]
    assert payload["labels"] == ["inbox", "work"]
    assert payload["unread"] is True
    assert payload["received_time"] == "2026-07-04T10:00:00"
    assert "mock" in payload["warnings"]


def test_permission_auto_allowed_list_emails(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "list_emails")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_auto_allowed_search_emails(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "search_emails")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_auto_allowed_read_email(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "read_email")
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_confirmation_send_email(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "send_email")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_compose_email(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "compose_email")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_delete_email(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "delete_email")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_archive_email(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "archive_email")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_mark_read(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "mark_read")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_confirmation_mark_unread(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "mark_unread")
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_permission_blocked_configure_account(manager: PermissionManager) -> None:
    result = manager.evaluate("email", "configure_account")
    assert result.level == PermissionLevel.BLOCKED


def test_email_tool_registered_in_tool_manager() -> None:
    manager = ToolManager()
    assert manager.registry.get("email") is not None
    schema = manager.registry.get("email").schema
    assert schema.name == "email"


def test_email_tool_run_list_emails(email_tool: EmailTool) -> None:
    result = email_tool.run(action="list_emails")
    assert result.success
    assert result.source == "email"
    assert result.metadata["connector"] == "email"


def test_evaluate_email_permission_aliases() -> None:
    evaluation = evaluate_email_permission("list")
    assert evaluation.level.value == "auto_allowed"

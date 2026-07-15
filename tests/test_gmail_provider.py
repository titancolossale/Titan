# =====================================
# Titan Gmail Provider Tests
# =====================================

"""Tests for Phase 15.2 — Gmail backend with mocked API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.connectors.email_backend_factory import create_email_backend
from tools.connectors.email_connector import EmailConnector
from tools.connectors.email_validator import EmailValidationCode, validate_email_config
from tools.connectors.gmail_provider import GmailProvider, _gmail_message_to_stored


@pytest.fixture
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def gmail_provider(mock_service: MagicMock) -> GmailProvider:
    return GmailProvider(mock_service)


def _sample_gmail_message(
    *,
    message_id: str = "msg-123",
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
    to_addr: str = "recipient@example.com",
    body: str = "Hello world",
    label_ids: list[str] | None = None,
) -> dict:
    import base64

    encoded = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "id": message_id,
        "threadId": "thread-1",
        "labelIds": label_ids or ["INBOX", "UNREAD"],
        "internalDate": "1720089000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": encoded, "size": len(body)},
        },
    }


def test_gmail_list_emails(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.list.return_value.execute.return_value = {
        "messages": [{"id": "msg-1"}, {"id": "msg-2"}],
    }
    messages_api.get.side_effect = [
        MagicMock(execute=MagicMock(return_value=_sample_gmail_message(message_id="msg-1"))),
        MagicMock(execute=MagicMock(return_value=_sample_gmail_message(message_id="msg-2"))),
    ]
    mock_service.users.return_value.messages.return_value = messages_api

    emails = gmail_provider.list_emails(limit=2)
    assert len(emails) == 2
    assert emails[0].message_id == "msg-1"
    assert emails[0].subject == "Test Subject"
    assert emails[0].unread is True


def test_gmail_search_emails(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.list.return_value.execute.return_value = {
        "messages": [{"id": "msg-search"}],
    }
    messages_api.get.return_value.execute.return_value = _sample_gmail_message(
        message_id="msg-search",
        subject="Titan search hit",
    )
    mock_service.users.return_value.messages.return_value = messages_api

    emails = gmail_provider.search_emails("Titan")
    assert len(emails) == 1
    assert "Titan" in emails[0].subject


def test_gmail_read_email(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.get.return_value.execute.return_value = _sample_gmail_message(
        message_id="msg-read",
        body="Full body content",
    )
    mock_service.users.return_value.messages.return_value = messages_api

    email = gmail_provider.read_email("msg-read")
    assert email is not None
    assert email.message_id == "msg-read"
    assert email.body == "Full body content"


def test_gmail_compose_email(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    drafts_api = MagicMock()
    drafts_api.create.return_value.execute.return_value = {
        "id": "draft-1",
        "message": {"id": "msg-draft"},
    }
    messages_api = MagicMock()
    messages_api.get.return_value.execute.return_value = _sample_gmail_message(
        message_id="msg-draft",
        subject="Draft subject",
        label_ids=["DRAFT"],
    )
    users_api = MagicMock()
    users_api.drafts.return_value = drafts_api
    users_api.messages.return_value = messages_api
    mock_service.users.return_value = users_api

    draft = gmail_provider.compose_email(
        recipients=["to@example.com"],
        subject="Draft subject",
        body="Draft body",
    )
    assert draft.message_id == "msg-draft"
    assert draft.status == "draft"


def test_gmail_send_email(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.send.return_value.execute.return_value = {"id": "msg-sent"}
    messages_api.get.return_value.execute.return_value = _sample_gmail_message(
        message_id="msg-sent",
        subject="Sent subject",
        label_ids=["SENT"],
    )
    mock_service.users.return_value.messages.return_value = messages_api

    sent = gmail_provider.send_email(
        recipients=["to@example.com"],
        subject="Sent subject",
        body="Sent body",
    )
    assert sent.message_id == "msg-sent"
    assert sent.status == "sent"


def test_gmail_archive_email(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.modify.return_value.execute.return_value = {"id": "msg-arc"}
    mock_service.users.return_value.messages.return_value = messages_api

    assert gmail_provider.archive_email("msg-arc") is True
    messages_api.modify.assert_called_once()


def test_gmail_mark_read(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.modify.return_value.execute.return_value = {"id": "msg-rd"}
    mock_service.users.return_value.messages.return_value = messages_api

    assert gmail_provider.mark_read("msg-rd") is True


def test_gmail_delete_email(gmail_provider: GmailProvider, mock_service: MagicMock) -> None:
    messages_api = MagicMock()
    messages_api.trash.return_value.execute.return_value = {"id": "msg-del"}
    mock_service.users.return_value.messages.return_value = messages_api

    assert gmail_provider.delete_email("msg-del") is True


def test_gmail_message_to_stored_parses_headers() -> None:
    stored = _gmail_message_to_stored(_sample_gmail_message())
    assert stored.sender == "sender@example.com"
    assert stored.recipients == ["recipient@example.com"]
    assert stored.folder == "inbox"
    assert stored.unread is True


def test_validate_gmail_config_missing_token(tmp_path: Path) -> None:
    secret_path = tmp_path / "client_secret.json"
    secret_path.write_text(
        json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}),
        encoding="utf-8",
    )
    token_path = tmp_path / "token.json"

    result = validate_email_config(
        enabled=True,
        timeout_seconds=30.0,
        provider="gmail",
        gmail_enabled=True,
        client_secret_path=secret_path,
        token_path=token_path,
    )
    assert not result.ok
    assert result.code == EmailValidationCode.GMAIL_MISSING_TOKEN


def test_create_email_backend_gmail_from_config() -> None:
    mock_provider = MagicMock()
    mock_provider.provider_name = "gmail"
    with patch(
        "tools.connectors.gmail_provider.GmailProvider.from_config",
        return_value=mock_provider,
    ):
        backend = create_email_backend(provider="gmail", gmail_enabled=True)
    assert backend.provider_name == "gmail"


def test_connector_send_email_mock_backend_blocked() -> None:
    backend = MagicMock()
    backend.provider_name = "mock"
    backend.send_email.side_effect = ValueError("mock send blocked")
    email_connector = EmailConnector(enabled=True, backend=backend)

    outcome = email_connector.execute(
        "send_email",
        {
            "recipients": ["to@example.com"],
            "subject": "Hi",
            "confirmed": True,
        },
    )
    assert not outcome.success
    assert "mock" in outcome.error.lower()

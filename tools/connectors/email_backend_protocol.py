# =====================================
# Titan Email Backend Protocol
# =====================================

"""Provider-independent email backend contract (Phase 15.1)."""

from __future__ import annotations

from typing import Protocol

from tools.connectors.email_backend import StoredEmail


class EmailBackend(Protocol):
    """Backend interface consumed by EmailConnector — no Gmail imports here."""

    provider_name: str

    def list_emails(
        self,
        *,
        folder: str | None = None,
        limit: int | None = None,
        unread_only: bool = False,
    ) -> list[StoredEmail]: ...

    def search_emails(
        self,
        query: str,
        *,
        folder: str | None = None,
    ) -> list[StoredEmail]: ...

    def read_email(self, message_id: str) -> StoredEmail | None: ...

    def compose_email(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> StoredEmail: ...

    def send_email(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        draft_id: str | None = None,
    ) -> StoredEmail: ...

    def delete_email(self, message_id: str) -> bool: ...

    def archive_email(self, message_id: str) -> bool: ...

    def mark_read(self, message_id: str) -> bool: ...

    def mark_unread(self, message_id: str) -> bool: ...

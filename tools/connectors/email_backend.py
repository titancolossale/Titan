# =====================================
# Titan Email Backend
# =====================================

"""In-memory email backend for provider-independent Email connector (Phase 15.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class StoredEmail:
    """Internal email record."""

    message_id: str
    sender: str
    recipients: list[str] = field(default_factory=list)
    subject: str = ""
    preview: str = ""
    body: str = ""
    attachments: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    unread: bool = False
    received_time: str = ""
    folder: str = "inbox"
    status: str = "received"


class InMemoryEmailBackend:
    """Mock email storage — no external provider integration (Phase 15.1)."""

    provider_name = "mock"

    def __init__(self) -> None:
        self._emails: dict[str, StoredEmail] = {}
        self._drafts: dict[str, StoredEmail] = {}
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """Populate default sample emails for development/tests."""
        self._emails.clear()
        self._drafts.clear()
        self._add_email(
            sender="ibrahim@example.com",
            recipients=["nolan@example.com"],
            subject="Revue Phase 14 — Calendar",
            body=(
                "Salut Nolan,\n\n"
                "Le connecteur Calendar est prêt. On enchaîne sur Email ?\n\n"
                "— Ibrahim"
            ),
            labels=["inbox", "work"],
            unread=True,
            received_time="2026-07-04T08:30:00",
        )
        self._add_email(
            sender="notifications@github.com",
            recipients=["nolan@example.com"],
            subject="[Titan] PR #42 merged",
            body="Your pull request Titan Phase 14 has been merged into main.",
            labels=["inbox", "github"],
            unread=False,
            received_time="2026-07-03T22:15:00",
        )
        self._add_email(
            sender="nolan@example.com",
            recipients=["ibrahim@example.com"],
            subject="Plan Phase 15 — Email Connector",
            body="Voici le plan pour le connecteur email V1.",
            labels=["sent"],
            unread=False,
            received_time="2026-07-02T14:00:00",
            folder="sent",
        )
        self._add_email(
            sender="newsletter@example.com",
            recipients=["nolan@example.com"],
            subject="Weekly digest — AI tools",
            body="Top stories this week in AI tooling and agents.",
            labels=["inbox", "newsletter"],
            unread=True,
            received_time="2026-07-01T09:00:00",
        )

    def _add_email(
        self,
        *,
        sender: str,
        recipients: list[str],
        subject: str,
        body: str,
        labels: list[str] | None = None,
        unread: bool = False,
        received_time: str = "",
        folder: str = "inbox",
        attachments: list[str] | None = None,
    ) -> StoredEmail:
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        preview = body[:120].replace("\n", " ").strip()
        email = StoredEmail(
            message_id=message_id,
            sender=sender,
            recipients=list(recipients),
            subject=subject,
            preview=preview,
            body=body,
            attachments=list(attachments or []),
            labels=list(labels or [folder]),
            unread=unread,
            received_time=received_time,
            folder=folder,
            status="received",
        )
        self._emails[message_id] = email
        return email

    def list_emails(
        self,
        *,
        folder: str | None = None,
        limit: int | None = None,
        unread_only: bool = False,
    ) -> list[StoredEmail]:
        emails = list(self._emails.values())
        if folder:
            emails = [email for email in emails if email.folder == folder]
        if unread_only:
            emails = [email for email in emails if email.unread]
        emails.sort(key=lambda item: item.received_time, reverse=True)
        if limit is not None and limit > 0:
            emails = emails[:limit]
        return emails

    def search_emails(
        self,
        query: str,
        *,
        folder: str | None = None,
    ) -> list[StoredEmail]:
        needle = query.strip().lower()
        if not needle:
            return self.list_emails(folder=folder)
        results: list[StoredEmail] = []
        for email in self._emails.values():
            if folder and email.folder != folder:
                continue
            haystack = " ".join(
                [
                    email.sender,
                    email.subject,
                    email.body,
                    email.preview,
                    " ".join(email.recipients),
                    " ".join(email.labels),
                ],
            ).lower()
            if needle in haystack:
                results.append(email)
        results.sort(key=lambda item: item.received_time, reverse=True)
        return results

    def read_email(self, message_id: str) -> StoredEmail | None:
        return self._emails.get(message_id)

    def compose_email(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> StoredEmail:
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        all_recipients = list(recipients)
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)
        preview = body[:120].replace("\n", " ").strip()
        draft = StoredEmail(
            message_id=draft_id,
            sender="nolan@example.com",
            recipients=all_recipients,
            subject=subject,
            preview=preview,
            body=body,
            labels=["draft"],
            unread=False,
            received_time="",
            folder="drafts",
            status="draft",
        )
        self._drafts[draft_id] = draft
        return draft

    def send_email(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        draft_id: str | None = None,
    ) -> StoredEmail:
        raise ValueError(
            "Envoi d'email non disponible sur le backend mock. "
            "Configurez TITAN_EMAIL_PROVIDER=gmail avec OAuth (python main.py email-auth)."
        )

    def delete_email(self, message_id: str) -> bool:
        if message_id in self._emails:
            del self._emails[message_id]
            return True
        if message_id in self._drafts:
            del self._drafts[message_id]
            return True
        return False

    def archive_email(self, message_id: str) -> bool:
        email = self._emails.get(message_id)
        if email is None:
            return False
        email.folder = "archive"
        if "archive" not in email.labels:
            email.labels.append("archive")
        if "inbox" in email.labels:
            email.labels.remove("inbox")
        return True

    def mark_read(self, message_id: str) -> bool:
        email = self._emails.get(message_id)
        if email is None:
            return False
        email.unread = False
        return True

    def mark_unread(self, message_id: str) -> bool:
        email = self._emails.get(message_id)
        if email is None:
            return False
        email.unread = True
        return True

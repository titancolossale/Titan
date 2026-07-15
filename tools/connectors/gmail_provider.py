# =====================================
# Titan Gmail Provider
# =====================================

"""Gmail API backend for EmailConnector (Phase 15.2).

EmailConnector and upstream layers depend only on the backend interface —
no Google imports outside this module and gmail_oauth.py.
"""

from __future__ import annotations

import base64
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Any

from tools.connectors.email_backend import StoredEmail
from tools.connectors.gmail_oauth import GMAIL_SCOPES, load_gmail_credentials

_FOLDER_LABELS: dict[str, str] = {
    "inbox": "INBOX",
    "sent": "SENT",
    "drafts": "DRAFT",
    "spam": "SPAM",
    "trash": "TRASH",
}


class GmailProvider:
    """Gmail backend implementing the EmailConnector backend contract."""

    provider_name = "gmail"

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_credentials(cls, credentials: Any) -> GmailProvider:
        """Build a provider from authorized Google credentials."""
        from googleapiclient.discovery import build

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )
        return cls(service)

    @classmethod
    def from_config(cls) -> GmailProvider:
        """Build a provider using configured token and client secret paths."""
        credentials = load_gmail_credentials(scopes=GMAIL_SCOPES)
        if credentials is None:
            raise ValueError(
                "Token Gmail absent ou expiré. "
                "Lancez : python main.py email-auth"
            )
        return cls.from_credentials(credentials)

    def list_emails(
        self,
        *,
        folder: str | None = None,
        limit: int | None = None,
        unread_only: bool = False,
    ) -> list[StoredEmail]:
        label_ids = self._resolve_label_ids(folder)
        query_parts: list[str] = []
        if unread_only:
            query_parts.append("is:unread")
        request_kwargs: dict[str, Any] = {
            "userId": "me",
            "maxResults": min(limit or 50, 100),
        }
        if label_ids:
            request_kwargs["labelIds"] = label_ids
        if query_parts:
            request_kwargs["q"] = " ".join(query_parts)

        response = self._service.users().messages().list(**request_kwargs).execute()
        messages = response.get("messages", [])
        emails: list[StoredEmail] = []
        for item in messages:
            stored = self.read_email(item["id"])
            if stored is not None:
                emails.append(stored)
        return emails

    def search_emails(
        self,
        query: str,
        *,
        folder: str | None = None,
    ) -> list[StoredEmail]:
        needle = query.strip()
        if not needle:
            return self.list_emails(folder=folder)

        label_ids = self._resolve_label_ids(folder)
        request_kwargs: dict[str, Any] = {
            "userId": "me",
            "q": needle,
            "maxResults": 50,
        }
        if label_ids:
            request_kwargs["labelIds"] = label_ids

        response = self._service.users().messages().list(**request_kwargs).execute()
        emails: list[StoredEmail] = []
        for item in response.get("messages", []):
            stored = self.read_email(item["id"])
            if stored is not None:
                emails.append(stored)
        return emails

    def read_email(self, message_id: str) -> StoredEmail | None:
        from googleapiclient.errors import HttpError

        try:
            message = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise
        return _gmail_message_to_stored(message)

    def compose_email(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> StoredEmail:
        if not recipients:
            raise ValueError("Au moins un destinataire est requis.")
        raw = _build_mime_raw(
            recipients=recipients,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
        )
        draft = (
            self._service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        message_id = draft.get("message", {}).get("id", draft.get("id", ""))
        stored = self.read_email(message_id)
        if stored is None:
            return StoredEmail(
                message_id=message_id,
                sender="",
                recipients=list(recipients),
                subject=subject,
                preview=body[:120].replace("\n", " ").strip(),
                body=body,
                labels=["draft"],
                folder="drafts",
                status="draft",
            )
        return StoredEmail(
            message_id=stored.message_id,
            sender=stored.sender,
            recipients=stored.recipients,
            subject=stored.subject,
            preview=stored.preview,
            body=stored.body,
            attachments=stored.attachments,
            labels=["draft"],
            unread=stored.unread,
            received_time=stored.received_time,
            folder="drafts",
            status="draft",
        )

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
        if draft_id:
            sent = (
                self._service.users()
                .drafts()
                .send(userId="me", body={"id": draft_id})
                .execute()
            )
            message_id = sent.get("id", "")
        else:
            if not recipients:
                raise ValueError("Au moins un destinataire est requis.")
            raw = _build_mime_raw(
                recipients=recipients,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
            )
            sent = (
                self._service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            message_id = sent.get("id", "")

        stored = self.read_email(message_id)
        if stored is None:
            return StoredEmail(
                message_id=message_id,
                sender="",
                recipients=list(recipients),
                subject=subject,
                preview=body[:120].replace("\n", " ").strip(),
                body=body,
                labels=["sent"],
                folder="sent",
                status="sent",
            )
        return StoredEmail(
            message_id=stored.message_id,
            sender=stored.sender,
            recipients=stored.recipients or list(recipients),
            subject=stored.subject or subject,
            preview=stored.preview,
            body=stored.body or body,
            attachments=stored.attachments,
            labels=["sent"],
            unread=False,
            received_time=stored.received_time,
            folder="sent",
            status="sent",
        )

    def delete_email(self, message_id: str) -> bool:
        from googleapiclient.errors import HttpError

        try:
            self._service.users().messages().trash(
                userId="me",
                id=message_id,
            ).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return False
            raise
        return True

    def archive_email(self, message_id: str) -> bool:
        from googleapiclient.errors import HttpError

        try:
            self._service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return False
            raise
        return True

    def mark_read(self, message_id: str) -> bool:
        from googleapiclient.errors import HttpError

        try:
            self._service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return False
            raise
        return True

    def mark_unread(self, message_id: str) -> bool:
        from googleapiclient.errors import HttpError

        try:
            self._service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": ["UNREAD"]},
            ).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return False
            raise
        return True

    def _resolve_label_ids(self, folder: str | None) -> list[str]:
        if not folder:
            return ["INBOX"]
        normalized = folder.strip().lower()
        label = _FOLDER_LABELS.get(normalized)
        return [label] if label else []


def _build_mime_raw(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> str:
    message = MIMEMultipart()
    message["to"] = ", ".join(recipients)
    message["subject"] = subject
    if cc:
        message["cc"] = ", ".join(cc)
    if bcc:
        message["bcc"] = ", ".join(bcc)
    message.attach(MIMEText(body, "plain", "utf-8"))
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _gmail_message_to_stored(message: dict[str, Any]) -> StoredEmail:
    headers = {
        header["name"].lower(): header["value"]
        for header in message.get("payload", {}).get("headers", [])
    }
    sender = headers.get("from", "")
    to_header = headers.get("to", "")
    recipients = [
        addr.strip()
        for _, addr in [parseaddr(part) for part in to_header.split(",")]
        if addr.strip()
    ]
    subject = headers.get("subject", "")
    body, attachments = _extract_body_and_attachments(message.get("payload", {}))
    preview = body[:120].replace("\n", " ").strip()
    label_ids = message.get("labelIds", [])
    labels = [label.lower() for label in label_ids]
    unread = "UNREAD" in label_ids
    received_time = _format_internal_date(message.get("internalDate", ""))
    folder = _label_ids_to_folder(label_ids)
    return StoredEmail(
        message_id=message.get("id", ""),
        sender=sender,
        recipients=recipients,
        subject=subject,
        preview=preview,
        body=body,
        attachments=attachments,
        labels=labels,
        unread=unread,
        received_time=received_time,
        folder=folder,
        status="received",
    )


def _extract_body_and_attachments(
    payload: dict[str, Any],
) -> tuple[str, list[str]]:
    attachments: list[str] = []
    body = _extract_text_from_payload(payload, attachments)
    return body.strip(), attachments


def _extract_text_from_payload(
    payload: dict[str, Any],
    attachments: list[str],
) -> str:
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return _decode_base64url(data)
    if mime_type == "text/html" and not attachments:
        data = payload.get("body", {}).get("data", "")
        if data:
            html = _decode_base64url(data)
            return _strip_html(html)
    if mime_type.startswith("multipart/"):
        parts = payload.get("parts", [])
        plain_text = ""
        html_text = ""
        for part in parts:
            part_mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            if filename:
                attachments.append(filename)
                continue
            if part_mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    plain_text = _decode_base64url(data)
            elif part_mime == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html_text = _decode_base64url(data)
            elif part_mime.startswith("multipart/"):
                nested, _ = _extract_body_and_attachments(part)
                if nested:
                    return nested
        return plain_text or _strip_html(html_text)
    return ""


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _format_internal_date(value: str) -> str:
    if not value:
        return ""
    try:
        from datetime import datetime, timezone

        timestamp_ms = int(value)
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return dt.replace(tzinfo=None).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return value


def _label_ids_to_folder(label_ids: list[str]) -> str:
    if "DRAFT" in label_ids:
        return "drafts"
    if "SENT" in label_ids:
        return "sent"
    if "TRASH" in label_ids:
        return "trash"
    if "SPAM" in label_ids:
        return "spam"
    if "INBOX" in label_ids:
        return "inbox"
    if "INBOX" not in label_ids and label_ids:
        return "archive"
    return "inbox"

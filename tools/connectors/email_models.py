# =====================================
# Titan Email Models
# =====================================

"""Structured email results for the Email connector (Phase 15.1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class EmailMessage:
    """A single email message."""

    message_id: str
    sender: str
    recipients: tuple[str, ...] = ()
    subject: str = ""
    preview: str = ""
    body: str = ""
    attachments: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    unread: bool = False
    received_time: str = ""
    status: str = "received"


@dataclass(frozen=True)
class EmailResult:
    """Structured outcome from an Email connector operation."""

    message_id: str = ""
    sender: str = ""
    recipients: tuple[str, ...] = ()
    subject: str = ""
    preview: str = ""
    body: str = ""
    attachments: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    unread: bool = False
    received_time: str = ""
    status: str = "ok"
    warnings: tuple[str, ...] = ()
    emails: tuple[EmailMessage, ...] = ()
    draft_id: str = ""

    def to_json(self) -> str:
        """Serialize for ToolResult.data and logging."""
        payload = {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipients": list(self.recipients),
            "subject": self.subject,
            "preview": self.preview,
            "body": self.body,
            "attachments": list(self.attachments),
            "labels": list(self.labels),
            "unread": self.unread,
            "received_time": self.received_time,
            "status": self.status,
            "warnings": list(self.warnings),
            "emails": [asdict(email) for email in self.emails],
            "draft_id": self.draft_id,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [f"Statut : {self.status}"]
        if self.message_id:
            lines.append(f"Message : {self.message_id}")
        if self.sender:
            lines.append(f"Expéditeur : {self.sender}")
        if self.recipients:
            lines.append(f"Destinataires : {', '.join(self.recipients)}")
        if self.subject:
            lines.append(f"Objet : {self.subject}")
        if self.received_time:
            lines.append(f"Reçu : {self.received_time}")
        if self.labels:
            lines.append(f"Étiquettes : {', '.join(self.labels)}")
        if self.unread:
            lines.append("Non lu")
        if self.attachments:
            lines.append(f"Pièces jointes : {', '.join(self.attachments)}")
        if self.emails:
            lines.append(f"Emails trouvés : {len(self.emails)}")
        if self.draft_id:
            lines.append(f"Brouillon : {self.draft_id}")
        if self.warnings:
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        if self.preview:
            lines.append("")
            lines.append(self.preview[:200].strip())
        elif self.body:
            lines.append("")
            lines.append(self.body[:200].strip())
        return "\n".join(lines)


@dataclass
class EmailSessionState:
    """In-memory connector session tracking for mock backend state."""

    started: bool = False
    default_folder: str = "inbox"
    warnings: list[str] = field(default_factory=list)

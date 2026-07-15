# =====================================
# Titan Email Decision Layer
# =====================================

"""Decide when and how Titan uses the Email connector (Phase 15.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tools.connectors.email_connector import EmailConnector

_EMAIL_SIGNALS = (
    "email",
    "e-mail",
    "courriel",
    "mail",
    "boîte",
    "boite",
    "inbox",
    "messagerie",
    "message à",
    "message a",
)

_LIST_EMAILS_KEYWORDS = (
    "liste mes emails",
    "liste les emails",
    "list emails",
    "my inbox",
    "ma boîte",
    "ma boite",
    "mes emails",
    "mes courriels",
    "montre mes emails",
    "show my emails",
)

_READ_EMAIL_KEYWORDS = (
    "lis l'email",
    "lis l email",
    "read email",
    "lire l'email",
    "lire l email",
    "ouvre l'email",
    "ouvre l email",
    "open email",
)

_SEARCH_KEYWORDS = (
    "cherche",
    "chercher",
    "recherche",
    "search",
    "trouve",
    "find email",
)

_COMPOSE_KEYWORDS = (
    "rédige",
    "redige",
    "compose",
    "compose email",
    "écris un email",
    "ecris un email",
    "write an email",
    "nouveau message",
    "new email",
)

_SEND_KEYWORDS = (
    "envoie",
    "envoyer",
    "send email",
    "send an email",
    "envoie un email",
    "envoie un courriel",
)

_DELETE_KEYWORDS = (
    "supprime",
    "supprimer",
    "delete email",
    "efface",
    "effacer",
)

_ARCHIVE_KEYWORDS = (
    "archive",
    "archiver",
    "archive email",
)

_MARK_READ_KEYWORDS = (
    "marque comme lu",
    "mark as read",
    "marquer lu",
)

_MARK_UNREAD_KEYWORDS = (
    "marque comme non lu",
    "mark as unread",
    "marquer non lu",
)


class EmailDecision(str, Enum):
    """Outcome of the Email decision layer."""

    LIST_EMAILS = "list_emails"
    SEARCH_EMAILS = "search_emails"
    READ_EMAIL = "read_email"
    COMPOSE_EMAIL = "compose_email"
    SEND_EMAIL = "send_email"
    DELETE_EMAIL = "delete_email"
    ARCHIVE_EMAIL = "archive_email"
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    DO_NOT_USE_EMAIL = "do_not_use_email"


@dataclass(frozen=True)
class EmailDecisionResult:
    """Structured Email routing decision."""

    decision: EmailDecision
    reason: str
    message_id: str = ""
    query: str = ""
    recipients: str = ""
    subject: str = ""
    body: str = ""
    tool_params: tuple[tuple[str, object], ...] = ()

    def tool_params_dict(self) -> dict[str, object]:
        """Return params suitable for ToolRequest."""
        return dict(self.tool_params)


class EmailDecisionEngine:
    """Map natural language requests to Email connector actions."""

    def __init__(self, connector: EmailConnector | None = None) -> None:
        self._connector = connector or EmailConnector(enabled=True)

    def decide(self, message: str) -> EmailDecisionResult:
        """Return the Email action Titan should take for *message*."""
        lowered = message.lower().strip()
        if not any(signal in lowered for signal in _EMAIL_SIGNALS):
            return EmailDecisionResult(
                decision=EmailDecision.DO_NOT_USE_EMAIL,
                reason="Aucune intention email détectée.",
            )
        if not self._connector.is_configured:
            return EmailDecisionResult(
                decision=EmailDecision.DO_NOT_USE_EMAIL,
                reason="Connecteur Email désactivé ou non configuré.",
            )

        if any(kw in lowered for kw in _SEND_KEYWORDS):
            recipients = self._extract_recipients(message)
            params: list[tuple[str, object]] = [("action", "send_email")]
            if recipients:
                params.append(("recipients", recipients))
            subject = self._extract_subject(message)
            if subject:
                params.append(("subject", subject))
            return EmailDecisionResult(
                decision=EmailDecision.SEND_EMAIL,
                reason="Envoi d'email demandé.",
                recipients=recipients,
                subject=subject,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _DELETE_KEYWORDS):
            message_id = self._extract_message_id(message)
            params = [("action", "delete_email")]
            if message_id:
                params.append(("message_id", message_id))
            return EmailDecisionResult(
                decision=EmailDecision.DELETE_EMAIL,
                reason="Suppression d'email demandée.",
                message_id=message_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _ARCHIVE_KEYWORDS):
            message_id = self._extract_message_id(message)
            params = [("action", "archive_email")]
            if message_id:
                params.append(("message_id", message_id))
            return EmailDecisionResult(
                decision=EmailDecision.ARCHIVE_EMAIL,
                reason="Archivage d'email demandé.",
                message_id=message_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _MARK_READ_KEYWORDS):
            message_id = self._extract_message_id(message)
            params = [("action", "mark_read")]
            if message_id:
                params.append(("message_id", message_id))
            return EmailDecisionResult(
                decision=EmailDecision.MARK_READ,
                reason="Marquage comme lu demandé.",
                message_id=message_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _MARK_UNREAD_KEYWORDS):
            message_id = self._extract_message_id(message)
            params = [("action", "mark_unread")]
            if message_id:
                params.append(("message_id", message_id))
            return EmailDecisionResult(
                decision=EmailDecision.MARK_UNREAD,
                reason="Marquage comme non lu demandé.",
                message_id=message_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _COMPOSE_KEYWORDS):
            recipients = self._extract_recipients(message)
            subject = self._extract_subject(message)
            params = [("action", "compose_email")]
            if recipients:
                params.append(("recipients", recipients))
            if subject:
                params.append(("subject", subject))
            return EmailDecisionResult(
                decision=EmailDecision.COMPOSE_EMAIL,
                reason="Composition d'email demandée.",
                recipients=recipients,
                subject=subject,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _READ_EMAIL_KEYWORDS):
            message_id = self._extract_message_id(message)
            params = [("action", "read_email")]
            if message_id:
                params.append(("message_id", message_id))
            return EmailDecisionResult(
                decision=EmailDecision.READ_EMAIL,
                reason="Lecture d'email demandée.",
                message_id=message_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _SEARCH_KEYWORDS):
            query = self._extract_search_query(message)
            return self._result(
                EmailDecision.SEARCH_EMAILS,
                "Recherche d'emails demandée.",
                query=query or message.strip(),
            )

        if any(kw in lowered for kw in _LIST_EMAILS_KEYWORDS):
            params_list: list[tuple[str, object]] = [("action", "list_emails")]
            if "non lu" in lowered or "unread" in lowered:
                params_list.append(("unread_only", True))
            return EmailDecisionResult(
                decision=EmailDecision.LIST_EMAILS,
                reason="Liste des emails demandée.",
                tool_params=tuple(params_list),
            )

        return self._result(
            EmailDecision.LIST_EMAILS,
            "Intention email générale — liste des emails par défaut.",
        )

    def _result(
        self,
        decision: EmailDecision,
        reason: str,
        *,
        query: str = "",
    ) -> EmailDecisionResult:
        params: list[tuple[str, object]] = [("action", decision.value)]
        if query:
            params.append(("query", query))
        return EmailDecisionResult(
            decision=decision,
            reason=reason,
            query=query,
            tool_params=tuple(params),
        )

    @staticmethod
    def _extract_message_id(message: str) -> str:
        match = re.search(
            r"\b(?:message[_-]?id|msg[_-]?id)[=:\s]+([a-zA-Z0-9-]+)",
            message,
            re.I,
        )
        return match.group(1) if match else ""

    @staticmethod
    def _extract_recipients(message: str) -> str:
        match = re.search(
            r"(?:à|a|to)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            message,
            re.I,
        )
        return match.group(1) if match else ""

    @staticmethod
    def _extract_subject(message: str) -> str:
        for marker in ("objet:", "subject:", "sujet:"):
            lowered = message.lower()
            if marker in lowered:
                idx = lowered.index(marker)
                return message[idx + len(marker) :].strip()
        return ""

    @staticmethod
    def _extract_search_query(message: str) -> str:
        lowered = message.lower()
        for marker in (
            "de ",
            "from ",
            "contenant ",
            "containing ",
            "about ",
            "sur ",
            "pour ",
        ):
            if marker in lowered:
                idx = lowered.index(marker)
                return message[idx + len(marker) :].strip().rstrip(".")
        return message.strip()

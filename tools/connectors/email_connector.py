# =====================================
# Titan Email Connector
# =====================================

"""Email connector — provider-independent (Phase 15.1).

Gmail integration is injected via backend factory in Phase 15.2+; this module
never imports Gmail APIs directly.
"""

from __future__ import annotations

from tools.connectors.base_connector import ConnectorResult
from tools.connectors.email_backend import InMemoryEmailBackend, StoredEmail
from tools.connectors.email_backend_factory import backend_label, create_email_backend
from tools.connectors.email_backend_protocol import EmailBackend
from tools.connectors.email_models import EmailMessage, EmailResult, EmailSessionState
from tools.connectors.email_permissions import (
    EMAIL_SUPPORTED_ACTIONS,
    EmailPermissionLevel,
    evaluate_email_permission,
    is_confirmed,
    normalize_email_action,
)
from tools.connectors.email_validator import validate_email_config

_READ_ACTIONS = frozenset({
    "list_emails",
    "search_emails",
    "read_email",
})

_WRITE_ACTIONS = frozenset({
    "compose_email",
    "send_email",
    "delete_email",
    "archive_email",
    "mark_read",
    "mark_unread",
})

_SUPPORTED_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS


class EmailConnector:
    """Operate on emails via a pluggable backend with permission gating."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        backend: EmailBackend | InMemoryEmailBackend | None = None,
        provider: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._provider = provider
        if backend is None:
            validation = validate_email_config(
                enabled=enabled,
                timeout_seconds=timeout_seconds,
                provider=provider,
            )
            if validation.ok and validation.provider == "gmail":
                backend = create_email_backend(provider="gmail")
            else:
                backend = InMemoryEmailBackend()
        self._backend = backend
        self._backend_label = backend_label(backend)
        self._session = EmailSessionState()

    @property
    def connector_id(self) -> str:
        return "email"

    @property
    def backend(self) -> EmailBackend:
        return self._backend

    @property
    def is_configured(self) -> bool:
        if not self._enabled:
            return False
        effective_provider = (
            "mock" if self._backend_label == "mock" else (self._provider or None)
        )
        validation = validate_email_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
        )
        return validation.ok

    @property
    def session(self) -> EmailSessionState:
        return self._session

    def configuration_error(self) -> str:
        """Return a French error when the connector is not ready."""
        effective_provider = (
            "mock" if self._backend_label == "mock" else (self._provider or None)
        )
        result = validate_email_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
        )
        return result.message

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        validation = validate_email_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=self._provider,
        )
        if not validation.ok:
            return False, validation.message
        self._session.started = True
        try:
            email_count = len(self._backend.list_emails())
        except Exception as exc:
            return False, f"Échec de connexion au backend email : {exc}"
        backend_name = "Gmail" if self._backend_label == "gmail" else "mock"
        return True, (
            f"{validation.message} Backend {backend_name} : "
            f"{email_count} email(s) accessible(s)."
        )

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the connector implementation."""
        normalized = normalize_email_action(action)
        if normalized not in self.supported_actions():
            if normalized in EMAIL_SUPPORTED_ACTIONS - _SUPPORTED_ACTIONS:
                return ConnectorResult(
                    success=False,
                    action=action,
                    error=f"Action bloquée ou non implémentée : {action!r}",
                )
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non supportée : {action!r}",
            )
        if not self.is_configured:
            return ConnectorResult(
                success=False,
                action=action,
                error=self.configuration_error(),
            )
        permission = evaluate_email_permission(
            normalized,
            params,
            confirmed=is_confirmed(params),
        )
        if permission.level == EmailPermissionLevel.BLOCKED:
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        if (
            permission.level == EmailPermissionLevel.CONFIRMATION_REQUIRED
            and normalized in _WRITE_ACTIONS
        ):
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        self._session.started = True
        return self._execute_action(normalized, params)

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        dispatch = {
            "list_emails": self._list_emails,
            "search_emails": self._search_emails,
            "read_email": self._read_email,
            "compose_email": self._compose_email,
            "send_email": self._send_email,
            "delete_email": self._delete_email,
            "archive_email": self._archive_email,
            "mark_read": self._mark_read,
            "mark_unread": self._mark_unread,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non implémentée : {action!r}",
            )
        try:
            return handler(params)
        except ValueError as exc:
            return ConnectorResult(success=False, action=action, error=str(exc))

    def _list_emails(self, params: dict) -> ConnectorResult:
        folder = str(params.get("folder", self._session.default_folder)).strip() or None
        limit_raw = params.get("limit")
        limit = int(limit_raw) if limit_raw is not None else None
        unread_only = bool(params.get("unread_only", False))
        emails = self._backend.list_emails(
            folder=folder,
            limit=limit,
            unread_only=unread_only,
        )
        result = EmailResult(
            status="ok",
            emails=tuple(self._to_message_model(email) for email in emails),
            warnings=self._provider_warning(),
        )
        return self._success("list_emails", result)

    def _search_emails(self, params: dict) -> ConnectorResult:
        query = str(params.get("query", params.get("q", ""))).strip()
        folder = str(params.get("folder", "")).strip() or None
        emails = self._backend.search_emails(query, folder=folder)
        result = EmailResult(
            subject=query,
            status="ok",
            emails=tuple(self._to_message_model(email) for email in emails),
            warnings=self._provider_warning(),
        )
        return self._success("search_emails", result)

    def _read_email(self, params: dict) -> ConnectorResult:
        message_id = str(params.get("message_id", "")).strip()
        if not message_id:
            return ConnectorResult(
                success=False,
                action="read_email",
                error="Paramètre message_id requis.",
            )
        email = self._backend.read_email(message_id)
        if email is None:
            return ConnectorResult(
                success=False,
                action="read_email",
                error=f"Email introuvable : {message_id!r}",
            )
        model = self._to_message_model(email)
        result = EmailResult(
            message_id=model.message_id,
            sender=model.sender,
            recipients=model.recipients,
            subject=model.subject,
            preview=model.preview,
            body=model.body,
            attachments=model.attachments,
            labels=model.labels,
            unread=model.unread,
            received_time=model.received_time,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("read_email", result, target_path=message_id)

    def _compose_email(self, params: dict) -> ConnectorResult:
        recipients_raw = params.get("recipients", params.get("to", []))
        recipients = self._normalize_recipients(recipients_raw)
        if not recipients:
            return ConnectorResult(
                success=False,
                action="compose_email",
                error="Paramètre recipients (ou to) requis.",
            )
        subject = str(params.get("subject", "")).strip()
        body = str(params.get("body", params.get("content", ""))).strip()
        cc = self._normalize_recipients(params.get("cc", []))
        bcc = self._normalize_recipients(params.get("bcc", []))
        draft = self._backend.compose_email(
            recipients=recipients,
            subject=subject,
            body=body,
            cc=cc or None,
            bcc=bcc or None,
        )
        model = self._to_message_model(draft)
        warnings = self._provider_warning()
        if self._backend_label != "gmail":
            warnings = warnings + (
                "Brouillon local uniquement — envoi via Gmail requiert provider=gmail.",
            )
        result = EmailResult(
            message_id=model.message_id,
            draft_id=model.message_id,
            sender=model.sender,
            recipients=model.recipients,
            subject=model.subject,
            preview=model.preview,
            body=model.body,
            status="draft",
            warnings=warnings,
        )
        return self._success("compose_email", result, target_path=draft.message_id)

    def _send_email(self, params: dict) -> ConnectorResult:
        recipients_raw = params.get("recipients", params.get("to", []))
        recipients = self._normalize_recipients(recipients_raw)
        subject = str(params.get("subject", "")).strip()
        body = str(params.get("body", params.get("content", ""))).strip()
        cc = self._normalize_recipients(params.get("cc", []))
        bcc = self._normalize_recipients(params.get("bcc", []))
        draft_id = str(params.get("draft_id", "")).strip() or None

        if not draft_id and not recipients:
            return ConnectorResult(
                success=False,
                action="send_email",
                error="Paramètre recipients (ou to) ou draft_id requis.",
            )

        try:
            sent = self._backend.send_email(
                recipients=recipients,
                subject=subject,
                body=body,
                cc=cc or None,
                bcc=bcc or None,
                draft_id=draft_id,
            )
        except ValueError as exc:
            return ConnectorResult(
                success=False,
                action="send_email",
                error=str(exc),
            )

        model = self._to_message_model(sent)
        result = EmailResult(
            message_id=model.message_id,
            sender=model.sender,
            recipients=model.recipients,
            subject=model.subject,
            preview=model.preview,
            body=model.body,
            status="sent",
            warnings=self._provider_warning(),
        )
        return self._success("send_email", result, target_path=sent.message_id)

    def _delete_email(self, params: dict) -> ConnectorResult:
        message_id = str(params.get("message_id", "")).strip()
        if not message_id:
            return ConnectorResult(
                success=False,
                action="delete_email",
                error="Paramètre message_id requis.",
            )
        deleted = self._backend.delete_email(message_id)
        if not deleted:
            return ConnectorResult(
                success=False,
                action="delete_email",
                error=f"Email introuvable : {message_id!r}",
            )
        result = EmailResult(
            message_id=message_id,
            status="deleted",
            warnings=self._provider_warning(),
        )
        return self._success("delete_email", result, target_path=message_id)

    def _archive_email(self, params: dict) -> ConnectorResult:
        message_id = str(params.get("message_id", "")).strip()
        if not message_id:
            return ConnectorResult(
                success=False,
                action="archive_email",
                error="Paramètre message_id requis.",
            )
        archived = self._backend.archive_email(message_id)
        if not archived:
            return ConnectorResult(
                success=False,
                action="archive_email",
                error=f"Email introuvable : {message_id!r}",
            )
        result = EmailResult(
            message_id=message_id,
            status="archived",
            labels=("archive",),
            warnings=self._provider_warning(),
        )
        return self._success("archive_email", result, target_path=message_id)

    def _mark_read(self, params: dict) -> ConnectorResult:
        message_id = str(params.get("message_id", "")).strip()
        if not message_id:
            return ConnectorResult(
                success=False,
                action="mark_read",
                error="Paramètre message_id requis.",
            )
        updated = self._backend.mark_read(message_id)
        if not updated:
            return ConnectorResult(
                success=False,
                action="mark_read",
                error=f"Email introuvable : {message_id!r}",
            )
        result = EmailResult(
            message_id=message_id,
            unread=False,
            status="read",
            warnings=self._provider_warning(),
        )
        return self._success("mark_read", result, target_path=message_id)

    def _mark_unread(self, params: dict) -> ConnectorResult:
        message_id = str(params.get("message_id", "")).strip()
        if not message_id:
            return ConnectorResult(
                success=False,
                action="mark_unread",
                error="Paramètre message_id requis.",
            )
        updated = self._backend.mark_unread(message_id)
        if not updated:
            return ConnectorResult(
                success=False,
                action="mark_unread",
                error=f"Email introuvable : {message_id!r}",
            )
        result = EmailResult(
            message_id=message_id,
            unread=True,
            status="unread",
            warnings=self._provider_warning(),
        )
        return self._success("mark_unread", result, target_path=message_id)

    def _provider_warning(self) -> tuple[str, ...]:
        if self._backend_label == "gmail":
            return ()
        return ("Backend mock — aucun provider externe connecté.",)

    @staticmethod
    def _normalize_recipients(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @staticmethod
    def _to_message_model(email: StoredEmail) -> EmailMessage:
        return EmailMessage(
            message_id=email.message_id,
            sender=email.sender,
            recipients=tuple(email.recipients),
            subject=email.subject,
            preview=email.preview,
            body=email.body,
            attachments=tuple(email.attachments),
            labels=tuple(email.labels),
            unread=email.unread,
            received_time=email.received_time,
            status=email.status,
        )

    @staticmethod
    def _success(
        action: str,
        result: EmailResult,
        *,
        target_path: str = "",
    ) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            action=action,
            data=result.to_json(),
            target_path=target_path,
        )

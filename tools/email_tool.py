# =====================================
# Titan Email Tool
# =====================================

"""Email connector tool — provider-independent (Phase 15.1)."""

from __future__ import annotations

from config.settings import TITAN_EMAIL_ENABLED, TITAN_EMAIL_TIMEOUT_SECONDS
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.connectors.email_connector import EmailConnector
from tools.connectors.email_permissions import (
    EMAIL_AUTO_ALLOWED_ACTIONS,
    EMAIL_CONFIRMATION_REQUIRED_ACTIONS,
    normalize_email_action,
)
from tools.tool_result import ToolResult

_SUPPORTED_ACTIONS = EMAIL_AUTO_ALLOWED_ACTIONS | EMAIL_CONFIRMATION_REQUIRED_ACTIONS

_EMAIL_TOOL_DESCRIPTION = (
    "Connecteur email de Titan — provider-indépendant. "
    "Liste, recherche et lit les emails. La composition, l'envoi, la suppression, "
    "l'archivage et le marquage lu/non-lu nécessitent confirmed=true. "
    "Backend configurable : mock (défaut) ou Gmail via OAuth (Phase 15.2)."
)


class EmailTool(BaseTool):
    """Read and manage emails through the Email connector."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        connector: EmailConnector | None = None,
    ) -> None:
        is_enabled = TITAN_EMAIL_ENABLED if enabled is None else enabled
        resolved_timeout = (
            TITAN_EMAIL_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._connector = connector or EmailConnector(
            enabled=is_enabled,
            timeout_seconds=resolved_timeout,
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="email",
            description=_EMAIL_TOOL_DESCRIPTION,
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Action email : list_emails, search_emails, read_email, "
                        "compose_email, send_email, delete_email, archive_email, "
                        "mark_read, mark_unread."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="message_id",
                    param_type="string",
                    description="Identifiant du message email.",
                    required=False,
                ),
                ToolParameter(
                    name="folder",
                    param_type="string",
                    description="Dossier cible (inbox, sent, archive, drafts).",
                    required=False,
                ),
                ToolParameter(
                    name="query",
                    param_type="string",
                    description="Requête de recherche d'emails.",
                    required=False,
                ),
                ToolParameter(
                    name="recipients",
                    param_type="string",
                    description="Destinataires (liste ou adresses séparées par virgule).",
                    required=False,
                ),
                ToolParameter(
                    name="to",
                    param_type="string",
                    description="Alias pour recipients.",
                    required=False,
                ),
                ToolParameter(
                    name="subject",
                    param_type="string",
                    description="Objet de l'email.",
                    required=False,
                ),
                ToolParameter(
                    name="body",
                    param_type="string",
                    description="Corps de l'email.",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    param_type="integer",
                    description="Nombre maximum d'emails à retourner.",
                    required=False,
                ),
                ToolParameter(
                    name="unread_only",
                    param_type="boolean",
                    description="Ne retourner que les emails non lus.",
                    required=False,
                ),
                ToolParameter(
                    name="confirmed",
                    param_type="boolean",
                    description=(
                        "Confirmation utilisateur pour compose/send/delete/archive/"
                        "mark_read/mark_unread."
                    ),
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = normalize_email_action(str(params.get("action", "")).strip())
        if not action:
            return self._result(success=False, error="Paramètre action requis.")
        if action not in _SUPPORTED_ACTIONS:
            return self._result(
                success=False,
                error=f"Action non supportée : {action!r}",
            )

        exec_params = {
            key: value
            for key, value in params.items()
            if not str(key).startswith("_")
        }
        outcome = self._connector.execute(action, exec_params)
        metadata = {
            "connector": self._connector.connector_id,
            "action": action,
            "target_path": outcome.target_path,
            "email_configured": self._connector.is_configured,
            "session_started": self._connector.session.started,
        }
        return ToolResult(
            tool_name=self.name,
            success=outcome.success,
            data=outcome.format_for_tool(),
            error=outcome.error if not outcome.success else "",
            source="email",
            metadata=metadata,
        )

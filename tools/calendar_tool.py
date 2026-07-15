# =====================================
# Titan Calendar Tool
# =====================================

"""Calendar scheduling tool — provider-independent connector (Phase 14.1)."""

from __future__ import annotations

from config.settings import TITAN_CALENDAR_ENABLED, TITAN_CALENDAR_TIMEOUT_SECONDS
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.calendar_permissions import (
    CALENDAR_AUTO_ALLOWED_ACTIONS,
    CALENDAR_CONFIRMATION_REQUIRED_ACTIONS,
    normalize_calendar_action,
)
from tools.tool_result import ToolResult

_SUPPORTED_ACTIONS = CALENDAR_AUTO_ALLOWED_ACTIONS | CALENDAR_CONFIRMATION_REQUIRED_ACTIONS

_CALENDAR_TOOL_DESCRIPTION = (
    "Connecteur calendrier de Titan — provider-indépendant (Phase 14.1–14.2). "
    "Liste les calendriers et événements, lit, recherche, détecte les conflits et "
    "trouve des créneaux libres. La création, modification et suppression nécessitent "
    "confirmed=true. Backend configurable : mock (défaut) ou Google Calendar via OAuth."
)


class CalendarTool(BaseTool):
    """Schedule and query calendars through the Calendar connector."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        connector: CalendarConnector | None = None,
    ) -> None:
        is_enabled = TITAN_CALENDAR_ENABLED if enabled is None else enabled
        resolved_timeout = (
            TITAN_CALENDAR_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._connector = connector or CalendarConnector(
            enabled=is_enabled,
            timeout_seconds=resolved_timeout,
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="calendar",
            description=_CALENDAR_TOOL_DESCRIPTION,
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Action calendrier : list_calendars, list_events, read_event, "
                        "search_events, create_event, update_event, delete_event, "
                        "detect_conflicts, find_free_time."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="calendar_id",
                    param_type="string",
                    description="Identifiant du calendrier cible.",
                    required=False,
                ),
                ToolParameter(
                    name="event_id",
                    param_type="string",
                    description="Identifiant de l'événement.",
                    required=False,
                ),
                ToolParameter(
                    name="title",
                    param_type="string",
                    description="Titre de l'événement.",
                    required=False,
                ),
                ToolParameter(
                    name="query",
                    param_type="string",
                    description="Requête de recherche d'événements.",
                    required=False,
                ),
                ToolParameter(
                    name="start_time",
                    param_type="string",
                    description="Début (ISO 8601).",
                    required=False,
                ),
                ToolParameter(
                    name="end_time",
                    param_type="string",
                    description="Fin (ISO 8601).",
                    required=False,
                ),
                ToolParameter(
                    name="duration_minutes",
                    param_type="integer",
                    description="Durée minimale pour find_free_time.",
                    required=False,
                    default=30,
                ),
                ToolParameter(
                    name="confirmed",
                    param_type="boolean",
                    description="Confirmation utilisateur pour create/update/delete.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = normalize_calendar_action(str(params.get("action", "")).strip())
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
            "calendar_configured": self._connector.is_configured,
            "session_started": self._connector.session.started,
        }
        return ToolResult(
            tool_name=self.name,
            success=outcome.success,
            data=outcome.format_for_tool(),
            error=outcome.error if not outcome.success else "",
            source="calendar",
            metadata=metadata,
        )

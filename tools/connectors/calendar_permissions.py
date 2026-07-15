# =====================================
# Titan Calendar Permissions
# =====================================

"""Calendar action permission tiers shared by connector and PermissionManager (Phase 14.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CalendarPermissionLevel(str, Enum):
    """Permission tier for a calendar action."""

    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


CALENDAR_AUTO_ALLOWED_ACTIONS = frozenset({
    "list_calendars",
    "list_events",
    "read_event",
    "search_events",
    "detect_conflicts",
    "find_free_time",
})

CALENDAR_CONFIRMATION_REQUIRED_ACTIONS = frozenset({
    "create_event",
    "update_event",
    "delete_event",
})

CALENDAR_BLOCKED_ACTIONS = frozenset({
    "share_calendar",
    "calendar_sharing",
    "configure_account",
    "account_configuration",
    "bulk_delete",
    "bulk_update",
    "bulk_clear",
})

CALENDAR_SUPPORTED_ACTIONS = (
    CALENDAR_AUTO_ALLOWED_ACTIONS
    | CALENDAR_CONFIRMATION_REQUIRED_ACTIONS
    | CALENDAR_BLOCKED_ACTIONS
)


@dataclass(frozen=True)
class CalendarPermissionEvaluation:
    """Outcome of calendar action permission classification."""

    level: CalendarPermissionLevel
    reason: str = ""
    confirmation_required: bool = False


def normalize_calendar_action(action: str) -> str:
    """Return the canonical action name used for permission lookup."""
    normalized = action.strip().lower()
    aliases = {
        "list": "list_events",
        "list_calendar": "list_calendars",
        "read": "read_event",
        "search": "search_events",
        "create": "create_event",
        "update": "update_event",
        "delete": "delete_event",
        "detect_scheduling_conflicts": "detect_conflicts",
        "availability": "find_free_time",
        "find_availability": "find_free_time",
    }
    return aliases.get(normalized, normalized)


def is_confirmed(params: dict | None) -> bool:
    """Return True when params carry an explicit user confirmation flag."""
    params_dict = dict(params or {})
    return bool(params_dict.get("confirmed") or params_dict.get("_confirmed"))


def is_destructive_bulk(params: dict | None) -> bool:
    """Return True when params request destructive bulk calendar operations."""
    params_dict = dict(params or {})
    if params_dict.get("bulk") is True and params_dict.get("destructive") is True:
        return True
    event_ids = params_dict.get("event_ids")
    if isinstance(event_ids, list) and len(event_ids) > 1:
        action = normalize_calendar_action(str(params_dict.get("action", "")))
        if action == "delete_event":
            return True
    return False


def evaluate_calendar_permission(
    action: str,
    params: dict | None = None,
    *,
    confirmed: bool = False,
) -> CalendarPermissionEvaluation:
    """Classify calendar action permission before execution."""
    normalized = normalize_calendar_action(action)

    if normalized in CALENDAR_BLOCKED_ACTIONS:
        return CalendarPermissionEvaluation(
            level=CalendarPermissionLevel.BLOCKED,
            reason=f"Action calendrier bloquée pour sécurité : {normalized!r}.",
        )

    if is_destructive_bulk(params):
        return CalendarPermissionEvaluation(
            level=CalendarPermissionLevel.BLOCKED,
            reason="Opérations destructives en masse sur le calendrier bloquées.",
        )

    if normalized in CALENDAR_CONFIRMATION_REQUIRED_ACTIONS:
        if confirmed:
            return CalendarPermissionEvaluation(
                level=CalendarPermissionLevel.AUTO_ALLOWED,
                reason="Action calendrier de modification confirmée.",
                confirmation_required=False,
            )
        return CalendarPermissionEvaluation(
            level=CalendarPermissionLevel.CONFIRMATION_REQUIRED,
            reason=(
                "Modification du calendrier — confirmation utilisateur requise."
            ),
            confirmation_required=True,
        )

    if normalized in CALENDAR_AUTO_ALLOWED_ACTIONS:
        return CalendarPermissionEvaluation(
            level=CalendarPermissionLevel.AUTO_ALLOWED,
            reason=f"Action calendrier autorisée : {normalized!r}.",
        )

    return CalendarPermissionEvaluation(
        level=CalendarPermissionLevel.BLOCKED,
        reason=f"Action calendrier non reconnue : {normalized!r}.",
    )

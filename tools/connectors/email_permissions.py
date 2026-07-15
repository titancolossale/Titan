# =====================================
# Titan Email Permissions
# =====================================

"""Email action permission tiers shared by connector and PermissionManager (Phase 15.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EmailPermissionLevel(str, Enum):
    """Permission tier for an email action."""

    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


EMAIL_AUTO_ALLOWED_ACTIONS = frozenset({
    "list_emails",
    "search_emails",
    "read_email",
})

EMAIL_CONFIRMATION_REQUIRED_ACTIONS = frozenset({
    "compose_email",
    "send_email",
    "delete_email",
    "archive_email",
    "mark_read",
    "mark_unread",
})

EMAIL_BLOCKED_ACTIONS = frozenset({
    "configure_account",
    "account_configuration",
    "bulk_delete",
    "bulk_archive",
    "export_all",
    "forward_all",
})

EMAIL_SUPPORTED_ACTIONS = (
    EMAIL_AUTO_ALLOWED_ACTIONS
    | EMAIL_CONFIRMATION_REQUIRED_ACTIONS
    | EMAIL_BLOCKED_ACTIONS
)


@dataclass(frozen=True)
class EmailPermissionEvaluation:
    """Outcome of email action permission classification."""

    level: EmailPermissionLevel
    reason: str = ""
    confirmation_required: bool = False


def normalize_email_action(action: str) -> str:
    """Return the canonical action name used for permission lookup."""
    normalized = action.strip().lower()
    aliases = {
        "list": "list_emails",
        "list_inbox": "list_emails",
        "search": "search_emails",
        "read": "read_email",
        "compose": "compose_email",
        "send": "send_email",
        "delete": "delete_email",
        "archive": "archive_email",
        "mark_as_read": "mark_read",
        "mark_as_unread": "mark_unread",
    }
    return aliases.get(normalized, normalized)


def is_confirmed(params: dict | None) -> bool:
    """Return True when params carry an explicit user confirmation flag."""
    params_dict = dict(params or {})
    return bool(params_dict.get("confirmed") or params_dict.get("_confirmed"))


def is_destructive_bulk(params: dict | None) -> bool:
    """Return True when params request destructive bulk email operations."""
    params_dict = dict(params or {})
    if params_dict.get("bulk") is True and params_dict.get("destructive") is True:
        return True
    message_ids = params_dict.get("message_ids")
    if isinstance(message_ids, list) and len(message_ids) > 1:
        action = normalize_email_action(str(params_dict.get("action", "")))
        if action in {"delete_email", "archive_email"}:
            return True
    return False


def evaluate_email_permission(
    action: str,
    params: dict | None = None,
    *,
    confirmed: bool = False,
) -> EmailPermissionEvaluation:
    """Classify email action permission before execution."""
    normalized = normalize_email_action(action)

    if normalized in EMAIL_BLOCKED_ACTIONS:
        return EmailPermissionEvaluation(
            level=EmailPermissionLevel.BLOCKED,
            reason=f"Action email bloquée pour sécurité : {normalized!r}.",
        )

    if is_destructive_bulk(params):
        return EmailPermissionEvaluation(
            level=EmailPermissionLevel.BLOCKED,
            reason="Opérations destructives en masse sur les emails bloquées.",
        )

    if normalized in EMAIL_CONFIRMATION_REQUIRED_ACTIONS:
        if confirmed:
            return EmailPermissionEvaluation(
                level=EmailPermissionLevel.AUTO_ALLOWED,
                reason="Action email de modification confirmée.",
                confirmation_required=False,
            )
        return EmailPermissionEvaluation(
            level=EmailPermissionLevel.CONFIRMATION_REQUIRED,
            reason="Modification des emails — confirmation utilisateur requise.",
            confirmation_required=True,
        )

    if normalized in EMAIL_AUTO_ALLOWED_ACTIONS:
        return EmailPermissionEvaluation(
            level=EmailPermissionLevel.AUTO_ALLOWED,
            reason=f"Action email autorisée : {normalized!r}.",
        )

    return EmailPermissionEvaluation(
        level=EmailPermissionLevel.BLOCKED,
        reason=f"Action email non reconnue : {normalized!r}.",
    )

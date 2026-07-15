# =====================================
# Titan Permission Manager
# =====================================

"""Action-level permission evaluation before tool execution (Phase 12.6 Batch 1 — P126-002)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tools.decision.models import DEFAULT_AVAILABLE_TOOLS, ToolDecisionReport
from tools.decision.obsidian_decision import ObsidianDecision
from tools.connectors.browser_permissions import (
    BROWSER_AUTO_ALLOWED_ACTIONS,
    BROWSER_BLOCKED_ACTIONS,
    BROWSER_CONFIRMATION_REQUIRED_ACTIONS,
    evaluate_browser_permission,
    normalize_browser_action,
)
from tools.connectors.calendar_permissions import (
    CALENDAR_AUTO_ALLOWED_ACTIONS,
    CALENDAR_BLOCKED_ACTIONS,
    CALENDAR_CONFIRMATION_REQUIRED_ACTIONS,
    evaluate_calendar_permission,
    normalize_calendar_action,
)
from tools.connectors.email_permissions import (
    EMAIL_AUTO_ALLOWED_ACTIONS,
    EMAIL_BLOCKED_ACTIONS,
    EMAIL_CONFIRMATION_REQUIRED_ACTIONS,
    evaluate_email_permission,
    normalize_email_action,
)
from tools.connectors.trading_permissions import (
    TRADING_AUTO_ALLOWED_ACTIONS,
    TRADING_BLOCKED_ACTIONS,
    TRADING_CONFIRMATION_REQUIRED_ACTIONS,
    evaluate_trading_permission,
    normalize_trading_action,
)

_READ_ACTIONS = frozenset({
    "read_file",
    "read_note",
    "list_notes",
    "list_folders",
    "list_directory",
    "get_metadata",
    "file_exists",
    "vault_health",
    "get_backlinks",
    "get_outlinks",
    "read_frontmatter",
    "list_tags",
    "list",
    "get_time",
})

_SEARCH_ACTIONS = frozenset({
    "search_notes",
    "search_files",
    "search",
})

_UPDATE_ACTIONS = frozenset({
    "write_file",
    "update_note",
    "patch_note",
    "update_frontmatter",
    "append",
    "prepend",
    "insert_under_heading",
    "replace_section",
    "update_checklist",
    "update_table",
    "replace",
})

_CREATE_ACTIONS = frozenset({
    "create_note",
    "create_folder",
})

_DELETE_ACTIONS = frozenset({
    "delete_note",
    "delete_file",
})

_VAULT_RESTRUCTURE_ACTIONS = frozenset({
    "rename_note",
    "move_note",
})

_EXTERNAL_COMMUNICATION_ACTIONS = frozenset({
    "send",
    "send_email",
    "send_message",
    "create_event",
    "update_event",
    "delete_event",
    "invite",
    "notify",
})

_TRADING_LEGACY_WRITE_ACTIONS = frozenset({
    "execute_order",
    "submit_trade",
    "close_position",
})

_TOOL_DEFAULT_ACTIONS: dict[str, str] = {
    "time": "get_time",
    "file_read": "read_file",
    "file_write": "write_file",
    "web_search": "search",
    "python_exec": "execute",
    "calendar": "list_events",
    "email": "list_emails",
    "trading": "get_positions",
    "github": "get_repository",
    "obsidian": "search_notes",
    "browser": "open_page",
}

_TOOL_ALLOWED_ACTIONS: dict[str, frozenset[str]] = {
    "file_read": frozenset({
        "read_file",
        "list_directory",
        "search_files",
        "get_metadata",
        "file_exists",
    }),
    "obsidian": frozenset({
        "read_note",
        "create_note",
        "update_note",
        "patch_note",
        "delete_note",
        "rename_note",
        "move_note",
        "create_folder",
        "list_notes",
        "list_folders",
        "search_notes",
        "get_backlinks",
        "get_outlinks",
        "read_frontmatter",
        "update_frontmatter",
        "list_tags",
        "vault_health",
    }),
    "browser": frozenset({
        "open_page",
        "navigate",
        "read_page",
        "extract_text",
        "search_public",
        "research_web",
        "compare_sources",
        "read_article",
        "scroll_page",
        "scroll",
        "go_back",
        "wait_for_element",
        "take_screenshot",
        "screenshot",
        "click_element",
        "click_button",
        "click",
        "type_text",
        "type",
        "type_into_input",
        "select_option",
        "select",
        "select_dropdown",
        "open_new_tab",
        "new_tab",
        "close_tab",
        "submit_form",
        "submit",
        "login",
        "download_file",
        "download",
        "upload_file",
        "upload",
        "execute_script",
        "execute_unknown_script",
        "bypass_security",
        "unsafe_click",
        "hidden_click",
        "click_hidden",
        "unsafe_automation",
    }),
    "calendar": frozenset({
        "list_calendars",
        "list_events",
        "read_event",
        "search_events",
        "detect_conflicts",
        "find_free_time",
        "create_event",
        "update_event",
        "delete_event",
        "share_calendar",
        "calendar_sharing",
        "configure_account",
        "account_configuration",
        "bulk_delete",
        "bulk_update",
        "bulk_clear",
    }),
    "email": frozenset({
        "list_emails",
        "search_emails",
        "read_email",
        "compose_email",
        "send_email",
        "delete_email",
        "archive_email",
        "mark_read",
        "mark_unread",
        "configure_account",
        "account_configuration",
        "bulk_delete",
        "bulk_archive",
        "export_all",
        "forward_all",
    }),
    "trading": frozenset({
        "list_accounts",
        "account_status",
        "get_positions",
        "get_orders",
        "get_price",
        "get_balance",
        "get_market_status",
        "place_order",
        "modify_order",
        "cancel_order",
        "flatten_position",
        "receive_alert",
        "parse_alert",
        "validate_alert",
        "identify_strategy",
        "extract_signal",
        "list_alerts",
        "get_latest_alert",
        "configure_provider",
        "reset_account",
        "bulk_close_all",
    }),
    "github": frozenset({
        "get_authenticated_user",
        "list_repositories",
        "get_repository",
        "list_branches",
        "get_branch",
        "list_commits",
        "get_commit",
        "list_issues",
        "get_issue",
        "list_pull_requests",
        "get_pull_request",
        "get_file_contents",
    }),
}


class PermissionLevel(str, Enum):
    """Action permission tier for tool orchestration."""

    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionPermissionResult:
    """Outcome of action-level permission evaluation."""

    level: PermissionLevel
    reason: str = ""
    action: str | None = None


def resolve_tool_action(
    tool_name: str,
    params: dict | None,
    decision_report: ToolDecisionReport | None = None,
) -> str:
    """Resolve the concrete action name for permission evaluation."""
    params_dict = dict(params or {})
    action = str(params_dict.get("action", "")).strip()
    if not action and decision_report is not None:
        if tool_name == "obsidian" and decision_report.obsidian_action:
            action = decision_report.obsidian_action
        elif tool_name == "browser" and decision_report.browser_action:
            action = decision_report.browser_action
        elif tool_name == "calendar" and decision_report.calendar_action:
            action = decision_report.calendar_action
        elif tool_name == "email" and decision_report.email_action:
            action = decision_report.email_action
        elif tool_name == "trading" and decision_report.trading_action:
            action = decision_report.trading_action
        elif tool_name == "file_read" and decision_report.file_operation:
            action = decision_report.file_operation
        elif tool_name == "github" and decision_report.github_operation:
            action = decision_report.github_operation
    if not action:
        if tool_name == "file_read" and params_dict.get("path"):
            return "read_file"
        if tool_name == "file_write":
            return "write_file"
        return _TOOL_DEFAULT_ACTIONS.get(tool_name, tool_name)
    return action


def is_bulk_action(
    tool_name: str,
    action: str,
    params: dict | None,
    decision_report: ToolDecisionReport | None = None,
) -> bool:
    """Return True when the invocation affects multiple targets."""
    params_dict = dict(params or {})
    if params_dict.get("bulk") is True:
        return True
    paths = params_dict.get("paths")
    if isinstance(paths, list) and len(paths) > 1:
        return True
    if decision_report is not None:
        if len(decision_report.affected_files) > 1:
            return True
        if decision_report.multi_step_execution and decision_report.steps_completed > 1:
            return True
    return action in {"apply_bulk", "bulk_update", "bulk_delete"}


@dataclass
class PermissionManager:
    """Evaluate whether a tool action is safe to execute without user confirmation."""

    allowed_tools: frozenset[str] = DEFAULT_AVAILABLE_TOOLS

    def evaluate(
        self,
        tool_name: str,
        action: str | None,
        params: dict | None = None,
        *,
        decision_report: ToolDecisionReport | None = None,
        confirmed: bool = False,
    ) -> ActionPermissionResult:
        """Classify action permission level before tool execution."""
        resolved_action = action or resolve_tool_action(tool_name, params, decision_report)

        if tool_name not in self.allowed_tools:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=f"Outil non autorisé : {tool_name!r}.",
                action=resolved_action,
            )

        allowed_actions = _TOOL_ALLOWED_ACTIONS.get(tool_name)
        if allowed_actions is not None and resolved_action not in allowed_actions:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=(
                    f"Action filesystem non autorisée : {resolved_action!r} "
                    f"pour {tool_name!r}."
                ),
                action=resolved_action,
            )

        if resolved_action in _TRADING_LEGACY_WRITE_ACTIONS:
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Action trading confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="Les ordres de trading nécessitent une confirmation explicite.",
                action=resolved_action,
            )

        if tool_name == "trading":
            return self._evaluate_trading_action(
                resolved_action,
                confirmed=confirmed,
                params=params,
            )

        if resolved_action in _DELETE_ACTIONS:
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Suppression confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="La suppression de fichiers ou notes nécessite une confirmation.",
                action=resolved_action,
            )

        if resolved_action in _VAULT_RESTRUCTURE_ACTIONS:
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Réorganisation vault confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="Le renommage ou déplacement de notes nécessite une confirmation.",
                action=resolved_action,
            )

        if is_bulk_action(tool_name, resolved_action, params, decision_report):
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Modification en masse confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="Les modifications en masse nécessitent une confirmation.",
                action=resolved_action,
            )

        if (
            tool_name == "calendar"
            and resolved_action in _EXTERNAL_COMMUNICATION_ACTIONS
        ) or resolved_action in _EXTERNAL_COMMUNICATION_ACTIONS:
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Communication externe confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="Les actions de communication externe nécessitent une confirmation.",
                action=resolved_action,
            )

        if tool_name == "python_exec":
            if confirmed:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Exécution Python confirmée par l'utilisateur.",
                    action=resolved_action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason="L'exécution de code Python nécessite une confirmation.",
                action=resolved_action,
            )

        if tool_name == "browser":
            return self._evaluate_browser_action(
                resolved_action,
                confirmed=confirmed,
                params=params,
            )

        if tool_name == "calendar":
            return self._evaluate_calendar_action(
                resolved_action,
                confirmed=confirmed,
                params=params,
            )

        if tool_name == "email":
            return self._evaluate_email_action(
                resolved_action,
                confirmed=confirmed,
                params=params,
            )

        if resolved_action in _CREATE_ACTIONS:
            return self._evaluate_create_action(
                tool_name,
                resolved_action,
                decision_report,
                confirmed=confirmed,
            )

        if (
            resolved_action in _READ_ACTIONS
            or resolved_action in _SEARCH_ACTIONS
            or resolved_action in _UPDATE_ACTIONS
        ):
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason=f"Action {resolved_action!r} autorisée automatiquement.",
                action=resolved_action,
            )

        if tool_name == "github":
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason="Lecture GitHub autorisée automatiquement.",
                action=resolved_action,
            )

        if tool_name == "web_search":
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason="Recherche web autorisée automatiquement.",
                action=resolved_action,
            )

        if tool_name == "time":
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason="Lecture de l'heure autorisée automatiquement.",
                action=resolved_action,
            )

        return ActionPermissionResult(
            level=PermissionLevel.BLOCKED,
            reason=f"Action non reconnue ou non autorisée : {resolved_action!r}.",
            action=resolved_action,
        )

    def _evaluate_create_action(
        self,
        tool_name: str,
        action: str,
        decision_report: ToolDecisionReport | None,
        *,
        confirmed: bool,
    ) -> ActionPermissionResult:
        """Create actions require Obsidian decision approval or user confirmation."""
        if confirmed:
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason="Création confirmée par l'utilisateur.",
                action=action,
            )

        if tool_name == "obsidian":
            obsidian_decision = (
                decision_report.obsidian_decision if decision_report else None
            )
            if obsidian_decision == ObsidianDecision.CREATE_NEW_NOTE.value:
                return ActionPermissionResult(
                    level=PermissionLevel.AUTO_ALLOWED,
                    reason="Création de note approuvée par la couche de décision Obsidian.",
                    action=action,
                )
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=(
                    "La création de notes nécessite une valeur durable confirmée "
                    "par la couche de décision Obsidian ou l'utilisateur."
                ),
                action=action,
            )

        return ActionPermissionResult(
            level=PermissionLevel.CONFIRMATION_REQUIRED,
            reason="La création de ressources nécessite une confirmation.",
            action=action,
        )

    def _evaluate_calendar_action(
        self,
        action: str,
        *,
        confirmed: bool,
        params: dict | None = None,
    ) -> ActionPermissionResult:
        """Classify Calendar connector action permissions (Phase 14.1)."""
        normalized = normalize_calendar_action(action)
        if normalized in CALENDAR_BLOCKED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=f"Action calendrier bloquée pour sécurité : {normalized!r}.",
                action=normalized,
            )

        evaluation = evaluate_calendar_permission(
            normalized,
            params,
            confirmed=confirmed,
        )
        if evaluation.level.value == PermissionLevel.BLOCKED.value:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=evaluation.reason,
                action=normalized,
            )
        if evaluation.confirmation_required:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in CALENDAR_AUTO_ALLOWED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in CALENDAR_CONFIRMATION_REQUIRED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        return ActionPermissionResult(
            level=PermissionLevel.BLOCKED,
            reason=f"Action calendrier non reconnue : {normalized!r}.",
            action=normalized,
        )

    def _evaluate_email_action(
        self,
        action: str,
        *,
        confirmed: bool,
        params: dict | None = None,
    ) -> ActionPermissionResult:
        """Classify Email connector action permissions (Phase 15.1)."""
        normalized = normalize_email_action(action)
        if normalized in EMAIL_BLOCKED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=f"Action email bloquée pour sécurité : {normalized!r}.",
                action=normalized,
            )

        evaluation = evaluate_email_permission(
            normalized,
            params,
            confirmed=confirmed,
        )
        if evaluation.level.value == PermissionLevel.BLOCKED.value:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=evaluation.reason,
                action=normalized,
            )
        if evaluation.confirmation_required:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in EMAIL_AUTO_ALLOWED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in EMAIL_CONFIRMATION_REQUIRED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        return ActionPermissionResult(
            level=PermissionLevel.BLOCKED,
            reason=f"Action email non reconnue : {normalized!r}.",
            action=normalized,
        )

    def _evaluate_trading_action(
        self,
        action: str,
        *,
        confirmed: bool,
        params: dict | None = None,
    ) -> ActionPermissionResult:
        """Classify Trading connector action permissions (Phase 16.1)."""
        normalized = normalize_trading_action(action)
        if normalized in TRADING_BLOCKED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=f"Action trading bloquée pour sécurité : {normalized!r}.",
                action=normalized,
            )

        evaluation = evaluate_trading_permission(
            normalized,
            params,
            confirmed=confirmed,
        )
        if evaluation.level.value == PermissionLevel.BLOCKED.value:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=evaluation.reason,
                action=normalized,
            )
        if evaluation.confirmation_required:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in TRADING_AUTO_ALLOWED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in TRADING_CONFIRMATION_REQUIRED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        return ActionPermissionResult(
            level=PermissionLevel.BLOCKED,
            reason=f"Action trading non reconnue : {normalized!r}.",
            action=normalized,
        )

    def _evaluate_browser_action(
        self,
        action: str,
        *,
        confirmed: bool,
        params: dict | None = None,
    ) -> ActionPermissionResult:
        """Classify Browser connector action permissions (Phase 13.3)."""
        normalized = normalize_browser_action(action)
        if normalized in BROWSER_BLOCKED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=f"Action navigateur bloquée pour sécurité : {normalized!r}.",
                action=normalized,
            )

        evaluation = evaluate_browser_permission(
            normalized,
            params,
            confirmed=confirmed,
        )
        if evaluation.level.value == PermissionLevel.BLOCKED.value:
            return ActionPermissionResult(
                level=PermissionLevel.BLOCKED,
                reason=evaluation.reason,
                action=normalized,
            )
        if evaluation.confirmation_required:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in BROWSER_AUTO_ALLOWED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.AUTO_ALLOWED,
                reason=evaluation.reason,
                action=normalized,
            )
        if normalized in BROWSER_CONFIRMATION_REQUIRED_ACTIONS:
            return ActionPermissionResult(
                level=PermissionLevel.CONFIRMATION_REQUIRED,
                reason=evaluation.reason,
                action=normalized,
            )
        return ActionPermissionResult(
            level=PermissionLevel.BLOCKED,
            reason=f"Action navigateur non reconnue : {normalized!r}.",
            action=normalized,
        )

    def requires_confirmation(
        self,
        tool_name: str,
        action: str | None,
        params: dict | None = None,
        *,
        decision_report: ToolDecisionReport | None = None,
        confirmed: bool = False,
    ) -> bool:
        """Return True when explicit user confirmation is required."""
        result = self.evaluate(
            tool_name,
            action,
            params,
            decision_report=decision_report,
            confirmed=confirmed,
        )
        return result.level == PermissionLevel.CONFIRMATION_REQUIRED

# =====================================
# Titan Browser Permissions
# =====================================

"""Browser action permission tiers shared by connector and PermissionManager (Phase 13.3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrowserPermissionLevel(str, Enum):
    """Permission tier for a browser action."""

    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


BROWSER_AUTO_ALLOWED_ACTIONS = frozenset({
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
})

BROWSER_CONFIRMATION_REQUIRED_ACTIONS = frozenset({
    "click_element",
    "click",
    "click_button",
    "type_text",
    "type",
    "type_into_input",
    "select_option",
    "select",
    "select_dropdown",
    "open_new_tab",
    "new_tab",
    "close_tab",
    "download_file",
    "download",
    "upload_file",
    "upload",
    "submit_form",
    "submit",
    "login",
})

BROWSER_BLOCKED_ACTIONS = frozenset({
    "bypass_security",
    "execute_script",
    "execute_unknown_script",
    "unsafe_click",
    "hidden_click",
    "click_hidden",
    "unsafe_automation",
})

BROWSER_SUPPORTED_ACTIONS = (
    BROWSER_AUTO_ALLOWED_ACTIONS
    | BROWSER_CONFIRMATION_REQUIRED_ACTIONS
    | BROWSER_BLOCKED_ACTIONS
)

_CREDENTIAL_MARKERS = ("password", "[type=password]", "[type='password']", "[type=\"password\"]")


@dataclass(frozen=True)
class BrowserPermissionEvaluation:
    """Outcome of browser action permission classification."""

    level: BrowserPermissionLevel
    reason: str = ""
    confirmation_required: bool = False


def normalize_browser_action(action: str) -> str:
    """Return the canonical action name used for permission lookup."""
    return action.strip().lower()


def is_credential_target(action: str, params: dict | None) -> bool:
    """Return True when the action targets credential entry without approval."""
    if normalize_browser_action(action) not in {
        "type_text",
        "type",
        "type_into_input",
    }:
        return False
    params_dict = dict(params or {})
    if params_dict.get("credential_approved") is True:
        return False
    input_type = str(params_dict.get("input_type", "")).strip().lower()
    if input_type == "password":
        return True
    selector = str(params_dict.get("selector", "")).strip().lower()
    return any(marker in selector for marker in _CREDENTIAL_MARKERS)


def is_unsafe_click_params(params: dict | None) -> bool:
    """Return True when click params request hidden or forced interaction."""
    params_dict = dict(params or {})
    if params_dict.get("force") is True:
        return True
    if params_dict.get("hidden") is True:
        return True
    if params_dict.get("unsafe") is True:
        return True
    return False


def evaluate_browser_permission(
    action: str,
    params: dict | None = None,
    *,
    confirmed: bool = False,
) -> BrowserPermissionEvaluation:
    """Classify browser action permission before execution."""
    normalized = normalize_browser_action(action)

    if normalized in BROWSER_BLOCKED_ACTIONS:
        return BrowserPermissionEvaluation(
            level=BrowserPermissionLevel.BLOCKED,
            reason=f"Action navigateur bloquée pour sécurité : {normalized!r}.",
        )

    if is_unsafe_click_params(params) and normalized in {
        "click_element",
        "click",
        "click_button",
    }:
        return BrowserPermissionEvaluation(
            level=BrowserPermissionLevel.BLOCKED,
            reason="Clic forcé ou caché bloqué — interaction non sécurisée.",
        )

    if is_credential_target(normalized, params):
        return BrowserPermissionEvaluation(
            level=BrowserPermissionLevel.BLOCKED,
            reason=(
                "Saisie d'identifiants bloquée sans approbation explicite "
                "(credential_approved=true)."
            ),
        )

    if normalized in BROWSER_CONFIRMATION_REQUIRED_ACTIONS:
        if confirmed:
            return BrowserPermissionEvaluation(
                level=BrowserPermissionLevel.AUTO_ALLOWED,
                reason="Action navigateur interactive confirmée.",
                confirmation_required=False,
            )
        return BrowserPermissionEvaluation(
            level=BrowserPermissionLevel.CONFIRMATION_REQUIRED,
            reason=(
                "Action navigateur interactive — confirmation utilisateur requise."
            ),
            confirmation_required=True,
        )

    if normalized in BROWSER_AUTO_ALLOWED_ACTIONS:
        return BrowserPermissionEvaluation(
            level=BrowserPermissionLevel.AUTO_ALLOWED,
            reason=f"Action navigateur autorisée : {normalized!r}.",
        )

    return BrowserPermissionEvaluation(
        level=BrowserPermissionLevel.BLOCKED,
        reason=f"Action navigateur non reconnue : {normalized!r}.",
    )


def is_confirmed(params: dict | None) -> bool:
    """Return True when params carry an explicit user confirmation flag."""
    params_dict = dict(params or {})
    return bool(params_dict.get("confirmed") or params_dict.get("_confirmed"))

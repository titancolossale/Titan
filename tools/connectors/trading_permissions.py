# =====================================
# Titan Trading Permissions
# =====================================

"""Trading action permission tiers shared by connector and PermissionManager (Phase 16.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TradingPermissionLevel(str, Enum):
    """Permission tier for a trading action."""

    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


TRADING_AUTO_ALLOWED_ACTIONS = frozenset({
    "list_accounts",
    "account_status",
    "get_positions",
    "get_orders",
    "get_price",
    "get_balance",
    "get_market_status",
    "get_pnl",
    "get_margin",
    # Phase 16.3 — signal-to-order draft (no execution)
    "draft_order_from_signal",
    "signal_to_order",
    # TradingView alert operations (Phase 16.2 — read-only, no order execution)
    "receive_alert",
    "parse_alert",
    "validate_alert",
    "identify_strategy",
    "extract_signal",
    "list_alerts",
    "get_latest_alert",
})

TRADING_CONFIRMATION_REQUIRED_ACTIONS = frozenset({
    "place_order",
    "modify_order",
    "cancel_order",
    "flatten_position",
    "execute_signal_order",
})

TRADING_BLOCKED_ACTIONS = frozenset({
    "configure_provider",
    "reset_account",
    "bulk_close_all",
})

TRADING_SUPPORTED_ACTIONS = (
    TRADING_AUTO_ALLOWED_ACTIONS
    | TRADING_CONFIRMATION_REQUIRED_ACTIONS
    | TRADING_BLOCKED_ACTIONS
)


@dataclass(frozen=True)
class TradingPermissionEvaluation:
    """Outcome of trading action permission classification."""

    level: TradingPermissionLevel
    reason: str = ""
    confirmation_required: bool = False


def normalize_trading_action(action: str) -> str:
    """Return the canonical action name used for permission lookup."""
    normalized = action.strip().lower()
    aliases = {
        "list": "list_accounts",
        "accounts": "list_accounts",
        "status": "account_status",
        "positions": "get_positions",
        "orders": "get_orders",
        "price": "get_price",
        "quote": "get_price",
    "balance": "get_balance",
    "market_status": "get_market_status",
    "market": "get_market_status",
    "pnl": "get_pnl",
    "margin": "get_margin",
    "place": "place_order",
        "order": "place_order",
        "modify": "modify_order",
        "cancel": "cancel_order",
        "flatten": "flatten_position",
        "close_position": "flatten_position",
        "close": "flatten_position",
        "draft_order": "draft_order_from_signal",
        "signal_to_order": "draft_order_from_signal",
        "execute_signal": "execute_signal_order",
        "alert": "receive_alert",
        "webhook": "receive_alert",
        "signals": "list_alerts",
        "latest_alert": "get_latest_alert",
    }
    return aliases.get(normalized, normalized)


def is_confirmed(params: dict | None) -> bool:
    """Return True when params carry an explicit user confirmation flag."""
    params_dict = dict(params or {})
    return bool(params_dict.get("confirmed") or params_dict.get("_confirmed"))


def is_bulk_close(params: dict | None) -> bool:
    """Return True when params request closing all positions at once."""
    params_dict = dict(params or {})
    if params_dict.get("bulk") is True and params_dict.get("close_all") is True:
        return True
    if normalize_trading_action(str(params_dict.get("action", ""))) == "bulk_close_all":
        return True
    return False


def evaluate_trading_permission(
    action: str,
    params: dict | None = None,
    *,
    confirmed: bool = False,
) -> TradingPermissionEvaluation:
    """Classify trading action permission before execution."""
    normalized = normalize_trading_action(action)

    if normalized in TRADING_BLOCKED_ACTIONS or is_bulk_close(params):
        return TradingPermissionEvaluation(
            level=TradingPermissionLevel.BLOCKED,
            reason=f"Action trading bloquée pour sécurité : {normalized!r}.",
        )

    if normalized in TRADING_CONFIRMATION_REQUIRED_ACTIONS:
        if confirmed:
            return TradingPermissionEvaluation(
                level=TradingPermissionLevel.AUTO_ALLOWED,
                reason="Action trading de modification confirmée.",
                confirmation_required=False,
            )
        return TradingPermissionEvaluation(
            level=TradingPermissionLevel.CONFIRMATION_REQUIRED,
            reason="Ordres et modifications de trading — confirmation utilisateur requise.",
            confirmation_required=True,
        )

    if normalized in TRADING_AUTO_ALLOWED_ACTIONS:
        return TradingPermissionEvaluation(
            level=TradingPermissionLevel.AUTO_ALLOWED,
            reason=f"Action trading autorisée : {normalized!r}.",
        )

    return TradingPermissionEvaluation(
        level=TradingPermissionLevel.BLOCKED,
        reason=f"Action trading non reconnue : {normalized!r}.",
    )

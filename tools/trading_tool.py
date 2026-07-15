# =====================================
# Titan Trading Tool
# =====================================

"""Trading connector tool — provider-independent (Phase 16.1)."""

from __future__ import annotations

from config.settings import TITAN_TRADING_ENABLED, TITAN_TRADING_TIMEOUT_SECONDS
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.connectors.trading_connector import TradingConnector
from tools.connectors.trading_permissions import (
    TRADING_AUTO_ALLOWED_ACTIONS,
    TRADING_CONFIRMATION_REQUIRED_ACTIONS,
    normalize_trading_action,
)
from tools.tool_result import ToolResult

_SUPPORTED_ACTIONS = (
    TRADING_AUTO_ALLOWED_ACTIONS | TRADING_CONFIRMATION_REQUIRED_ACTIONS
)

_TRADING_TOOL_DESCRIPTION = (
    "Connecteur trading de Titan — provider-indépendant. "
    "Liste les comptes, lit positions, ordres, prix et soldes. "
    "Reçoit et comprend les alertes TradingView (Phase 16.2). "
    "Les ordres (place, modify, cancel, flatten) nécessitent confirmed=true. "
    "Backend configurable : mock/paper (défaut), tradingview (alertes). "
    "Apex, Rithmic et NinjaTrader non connectés."
)


class TradingTool(BaseTool):
    """Read and manage trading accounts through the Trading connector."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        connector: TradingConnector | None = None,
    ) -> None:
        is_enabled = TITAN_TRADING_ENABLED if enabled is None else enabled
        resolved_timeout = (
            TITAN_TRADING_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._connector = connector or TradingConnector(
            enabled=is_enabled,
            timeout_seconds=resolved_timeout,
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="trading",
            description=_TRADING_TOOL_DESCRIPTION,
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Action trading : list_accounts, account_status, get_positions, "
                        "get_orders, get_price, get_balance, get_market_status, "
                        "receive_alert, parse_alert, validate_alert, identify_strategy, "
                        "extract_signal, list_alerts, get_latest_alert, "
                        "place_order, modify_order, cancel_order, flatten_position."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="account_id",
                    param_type="string",
                    description="Identifiant du compte trading.",
                    required=False,
                ),
                ToolParameter(
                    name="symbol",
                    param_type="string",
                    description="Symbole (ex. NQ, ES).",
                    required=False,
                ),
                ToolParameter(
                    name="market",
                    param_type="string",
                    description="Marché (ex. CME).",
                    required=False,
                ),
                ToolParameter(
                    name="timeframe",
                    param_type="string",
                    description="Timeframe pour get_price (ex. 1m, 5m).",
                    required=False,
                ),
                ToolParameter(
                    name="side",
                    param_type="string",
                    description="Côté de l'ordre : buy ou sell.",
                    required=False,
                ),
                ToolParameter(
                    name="quantity",
                    param_type="number",
                    description="Quantité pour place_order ou modify_order.",
                    required=False,
                ),
                ToolParameter(
                    name="order_type",
                    param_type="string",
                    description="Type d'ordre : market, limit.",
                    required=False,
                ),
                ToolParameter(
                    name="price",
                    param_type="number",
                    description="Prix limite pour place_order ou modify_order.",
                    required=False,
                ),
                ToolParameter(
                    name="order_id",
                    param_type="string",
                    description="Identifiant d'ordre pour modify_order ou cancel_order.",
                    required=False,
                ),
                ToolParameter(
                    name="status",
                    param_type="string",
                    description="Filtre de statut pour get_orders.",
                    required=False,
                ),
                ToolParameter(
                    name="confirmed",
                    param_type="boolean",
                    description=(
                        "Confirmation utilisateur pour place/modify/cancel/flatten."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="payload",
                    param_type="string",
                    description=(
                        "Corps d'alerte TradingView (JSON ou texte) pour receive/parse/validate."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="raw_message",
                    param_type="string",
                    description="Alias de payload pour alertes TradingView.",
                    required=False,
                ),
                ToolParameter(
                    name="webhook_secret",
                    param_type="string",
                    description="Secret webhook pour validation TradingView.",
                    required=False,
                ),
                ToolParameter(
                    name="strategy_name",
                    param_type="string",
                    description="Nom de stratégie pour extract_signal ou filtre get_latest_alert.",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    param_type="number",
                    description="Nombre max d'alertes pour list_alerts.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = normalize_trading_action(str(params.get("action", "")).strip())
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
            "trading_configured": self._connector.is_configured,
            "session_started": self._connector.session.started,
        }
        return ToolResult(
            tool_name=self.name,
            success=outcome.success,
            data=outcome.format_for_tool(),
            error=outcome.error if not outcome.success else "",
            source="trading",
            metadata=metadata,
        )

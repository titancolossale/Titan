# =====================================
# Titan Trading Decision Layer
# =====================================

"""Decide when and how Titan uses the Trading connector (Phase 16.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tools.connectors.trading_connector import TradingConnector

_TRADING_SIGNALS = (
    "trading",
    "trade",
    "ordre",
    "order",
    "position",
    "positions",
    "marché",
    "marche",
    "market",
    "futures",
    "future",
    "nq",
    "broker",
    "compte",
    "account",
    "paper",
    "solde",
    "balance",
    "pnl",
    "cotation",
    "quote",
    "prix",
)

_LIST_ACCOUNTS_KEYWORDS = (
    "liste mes comptes",
    "list accounts",
    "mes comptes",
    "mes comptes trading",
    "show accounts",
)

_ACCOUNT_STATUS_KEYWORDS = (
    "statut du compte",
    "account status",
    "état du compte",
    "etat du compte",
)

_POSITIONS_KEYWORDS = (
    "mes positions",
    "my positions",
    "position ouverte",
    "open positions",
    "montre mes positions",
    "show positions",
    "get positions",
)

_ORDERS_KEYWORDS = (
    "mes ordres",
    "my orders",
    "ordres ouverts",
    "open orders",
    "liste les ordres",
    "list orders",
)

_PRICE_KEYWORDS = (
    "prix",
    "price",
    "cotation",
    "quote",
    "dernier prix",
    "last price",
    "bid",
    "ask",
)

_BALANCE_KEYWORDS = (
    "solde",
    "balance",
    "marge",
    "margin",
    "capital",
)

_MARKET_STATUS_KEYWORDS = (
    "marché ouvert",
    "marche ouvert",
    "market open",
    "market status",
    "statut du marché",
    "statut du marche",
)

_PLACE_ORDER_KEYWORDS = (
    "place un ordre",
    "place order",
    "passer un ordre",
    "buy ",
    "sell ",
    "achète",
    "achete",
    "vends",
    "acheter",
    "vendre",
)

_CANCEL_ORDER_KEYWORDS = (
    "annule l'ordre",
    "annule l ordre",
    "cancel order",
    "annuler l'ordre",
)

_MODIFY_ORDER_KEYWORDS = (
    "modifie l'ordre",
    "modifie l ordre",
    "modify order",
    "modifier l'ordre",
)

_FLATTEN_KEYWORDS = (
    "ferme la position",
    "close position",
    "flatten",
    "aplatir",
    "clôturer",
    "cloturer",
)

_TRADINGVIEW_ALERT_KEYWORDS = (
    "tradingview",
    "alerte tradingview",
    "tradingview alert",
    "webhook tradingview",
    "dernière alerte",
    "derniere alerte",
    "latest alert",
    "liste les alertes",
    "list alerts",
    "signal tradingview",
    "alerte reçue",
    "alerte recue",
)

_RECEIVE_ALERT_KEYWORDS = (
    "reçois l'alerte",
    "recois l alerte",
    "receive alert",
    "webhook alert",
)

_PARSE_ALERT_KEYWORDS = (
    "parse l'alerte",
    "parse l alerte",
    "parse alert",
    "analyse l'alerte",
)

_VALIDATE_ALERT_KEYWORDS = (
    "valide l'alerte",
    "valide l alerte",
    "validate alert",
)

_LIST_ALERTS_KEYWORDS = (
    "liste les alertes",
    "list alerts",
    "mes alertes",
    "alertes tradingview",
)

_LATEST_ALERT_KEYWORDS = (
    "dernière alerte",
    "derniere alerte",
    "latest alert",
    "dernier signal",
)


class TradingDecision(str, Enum):
    """Outcome of the Trading decision layer."""

    LIST_ACCOUNTS = "list_accounts"
    ACCOUNT_STATUS = "account_status"
    GET_POSITIONS = "get_positions"
    GET_ORDERS = "get_orders"
    GET_PRICE = "get_price"
    GET_BALANCE = "get_balance"
    GET_MARKET_STATUS = "get_market_status"
    PLACE_ORDER = "place_order"
    MODIFY_ORDER = "modify_order"
    CANCEL_ORDER = "cancel_order"
    FLATTEN_POSITION = "flatten_position"
    RECEIVE_ALERT = "receive_alert"
    PARSE_ALERT = "parse_alert"
    VALIDATE_ALERT = "validate_alert"
    IDENTIFY_STRATEGY = "identify_strategy"
    EXTRACT_SIGNAL = "extract_signal"
    LIST_ALERTS = "list_alerts"
    GET_LATEST_ALERT = "get_latest_alert"
    DO_NOT_USE_TRADING = "do_not_use_trading"


@dataclass(frozen=True)
class TradingDecisionResult:
    """Structured Trading routing decision."""

    decision: TradingDecision
    reason: str
    account_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    order_id: str = ""
    market: str = ""
    tool_params: tuple[tuple[str, object], ...] = ()

    def tool_params_dict(self) -> dict[str, object]:
        """Return params suitable for ToolRequest."""
        return dict(self.tool_params)


class TradingDecisionEngine:
    """Map natural language requests to Trading connector actions."""

    def __init__(self, connector: TradingConnector | None = None) -> None:
        self._connector = connector or TradingConnector(enabled=True)

    def decide(self, message: str) -> TradingDecisionResult:
        """Return the Trading action Titan should take for *message*."""
        lowered = message.lower().strip()
        if not self._has_trading_signal(lowered):
            return TradingDecisionResult(
                decision=TradingDecision.DO_NOT_USE_TRADING,
                reason="Aucune intention trading détectée.",
            )
        if not self._connector.is_configured:
            return TradingDecisionResult(
                decision=TradingDecision.DO_NOT_USE_TRADING,
                reason="Connecteur Trading désactivé ou non configuré.",
            )

        symbol = self._extract_symbol(message)
        account_id = self._extract_account_id(message)
        market = self._extract_market(message)
        payload = self._extract_alert_payload(message)

        if any(kw in lowered for kw in _RECEIVE_ALERT_KEYWORDS) or (
            payload and "receive" in lowered
        ):
            params: list[tuple[str, object]] = [("action", "receive_alert")]
            if payload:
                params.append(("payload", payload))
            return TradingDecisionResult(
                decision=TradingDecision.RECEIVE_ALERT,
                reason="Réception d'alerte TradingView demandée.",
                symbol=symbol,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _PARSE_ALERT_KEYWORDS):
            params = [("action", "parse_alert")]
            if payload:
                params.append(("payload", payload))
            return TradingDecisionResult(
                decision=TradingDecision.PARSE_ALERT,
                reason="Analyse d'alerte TradingView demandée.",
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _VALIDATE_ALERT_KEYWORDS):
            params = [("action", "validate_alert")]
            if payload:
                params.append(("payload", payload))
            return TradingDecisionResult(
                decision=TradingDecision.VALIDATE_ALERT,
                reason="Validation d'alerte TradingView demandée.",
                tool_params=tuple(params),
            )

        if (
            ("identifie" in lowered and "stratég" in lowered)
            or ("identify" in lowered and "strategy" in lowered)
        ):
            params = [("action", "identify_strategy")]
            if payload:
                params.append(("payload", payload))
            return TradingDecisionResult(
                decision=TradingDecision.IDENTIFY_STRATEGY,
                reason="Identification de stratégie demandée.",
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in ("extrait le signal", "extract signal")):
            params = [("action", "extract_signal")]
            if payload:
                params.append(("payload", payload))
            return TradingDecisionResult(
                decision=TradingDecision.EXTRACT_SIGNAL,
                reason="Extraction de signal TradingView demandée.",
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _LIST_ALERTS_KEYWORDS):
            return TradingDecisionResult(
                decision=TradingDecision.LIST_ALERTS,
                reason="Liste des alertes TradingView demandée.",
                tool_params=(("action", "list_alerts"),),
            )

        if any(kw in lowered for kw in _LATEST_ALERT_KEYWORDS):
            params = [("action", "get_latest_alert")]
            if symbol:
                params.append(("symbol", symbol))
            return TradingDecisionResult(
                decision=TradingDecision.GET_LATEST_ALERT,
                reason="Dernière alerte TradingView demandée.",
                symbol=symbol,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _TRADINGVIEW_ALERT_KEYWORDS):
            return TradingDecisionResult(
                decision=TradingDecision.LIST_ALERTS,
                reason="Intention TradingView — liste des alertes.",
                tool_params=(("action", "list_alerts"),),
            )

        if any(kw in lowered for kw in _PLACE_ORDER_KEYWORDS):
            side = self._extract_side(message)
            quantity = self._extract_quantity(message)
            params: list[tuple[str, object]] = [("action", "place_order")]
            if symbol:
                params.append(("symbol", symbol))
            if side:
                params.append(("side", side))
            if quantity:
                params.append(("quantity", quantity))
            if account_id:
                params.append(("account_id", account_id))
            if market:
                params.append(("market", market))
            return TradingDecisionResult(
                decision=TradingDecision.PLACE_ORDER,
                reason="Placement d'ordre demandé.",
                symbol=symbol,
                side=side,
                quantity=quantity,
                account_id=account_id,
                market=market,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _CANCEL_ORDER_KEYWORDS):
            order_id = self._extract_order_id(message)
            params = [("action", "cancel_order")]
            if order_id:
                params.append(("order_id", order_id))
            return TradingDecisionResult(
                decision=TradingDecision.CANCEL_ORDER,
                reason="Annulation d'ordre demandée.",
                order_id=order_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _MODIFY_ORDER_KEYWORDS):
            order_id = self._extract_order_id(message)
            quantity = self._extract_quantity(message)
            params = [("action", "modify_order")]
            if order_id:
                params.append(("order_id", order_id))
            if quantity:
                params.append(("quantity", quantity))
            return TradingDecisionResult(
                decision=TradingDecision.MODIFY_ORDER,
                reason="Modification d'ordre demandée.",
                order_id=order_id,
                quantity=quantity,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _FLATTEN_KEYWORDS):
            params = [("action", "flatten_position")]
            if symbol:
                params.append(("symbol", symbol))
            if account_id:
                params.append(("account_id", account_id))
            if market:
                params.append(("market", market))
            return TradingDecisionResult(
                decision=TradingDecision.FLATTEN_POSITION,
                reason="Fermeture de position demandée.",
                symbol=symbol,
                account_id=account_id,
                market=market,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _ORDERS_KEYWORDS):
            params = [("action", "get_orders")]
            if account_id:
                params.append(("account_id", account_id))
            if symbol:
                params.append(("symbol", symbol))
            return TradingDecisionResult(
                decision=TradingDecision.GET_ORDERS,
                reason="Liste des ordres demandée.",
                account_id=account_id,
                symbol=symbol,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _POSITIONS_KEYWORDS):
            params = [("action", "get_positions")]
            if account_id:
                params.append(("account_id", account_id))
            if symbol:
                params.append(("symbol", symbol))
            return TradingDecisionResult(
                decision=TradingDecision.GET_POSITIONS,
                reason="Positions demandées.",
                account_id=account_id,
                symbol=symbol,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _BALANCE_KEYWORDS):
            params = [("action", "get_balance")]
            if account_id:
                params.append(("account_id", account_id))
            return TradingDecisionResult(
                decision=TradingDecision.GET_BALANCE,
                reason="Solde demandé.",
                account_id=account_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _MARKET_STATUS_KEYWORDS):
            params = [("action", "get_market_status")]
            params.append(("market", market or "CME"))
            return TradingDecisionResult(
                decision=TradingDecision.GET_MARKET_STATUS,
                reason="Statut du marché demandé.",
                market=market or "CME",
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _PRICE_KEYWORDS) or symbol:
            params = [("action", "get_price")]
            params.append(("symbol", symbol or "NQ"))
            if market:
                params.append(("market", market))
            return TradingDecisionResult(
                decision=TradingDecision.GET_PRICE,
                reason="Cotation demandée.",
                symbol=symbol or "NQ",
                market=market,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _ACCOUNT_STATUS_KEYWORDS):
            params = [("action", "account_status")]
            if account_id:
                params.append(("account_id", account_id))
            return TradingDecisionResult(
                decision=TradingDecision.ACCOUNT_STATUS,
                reason="Statut du compte demandé.",
                account_id=account_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _LIST_ACCOUNTS_KEYWORDS):
            return TradingDecisionResult(
                decision=TradingDecision.LIST_ACCOUNTS,
                reason="Liste des comptes demandée.",
                tool_params=(("action", "list_accounts"),),
            )

        return TradingDecisionResult(
            decision=TradingDecision.GET_POSITIONS,
            reason="Intention trading générale — positions par défaut.",
            tool_params=(("action", "get_positions"),),
        )

    @staticmethod
    def _has_trading_signal(lowered: str) -> bool:
        """Detect trading intent without false positives on short symbol tokens."""
        symbol_tokens = {"nq", "es", "ym", "rty", "cl", "gc"}
        long_signals = tuple(
            signal for signal in _TRADING_SIGNALS if signal not in symbol_tokens
        )
        if any(signal in lowered for signal in long_signals):
            return True
        return any(
            re.search(rf"\b{re.escape(token)}\b", lowered)
            for token in symbol_tokens
        )

    @staticmethod
    def _extract_symbol(message: str) -> str:
        match = re.search(r"\b(NQ|ES|YM|RTY|CL|GC|BTC|ETH)\b", message, re.I)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _extract_account_id(message: str) -> str:
        match = re.search(
            r"\b(?:account[_-]?id|compte)[=:\s]+([a-zA-Z0-9-]+)",
            message,
            re.I,
        )
        return match.group(1) if match else ""

    @staticmethod
    def _extract_order_id(message: str) -> str:
        match = re.search(
            r"\b(?:order[_-]?id|ordre)[=:\s]+([a-zA-Z0-9-]+)",
            message,
            re.I,
        )
        return match.group(1) if match else ""

    @staticmethod
    def _extract_market(message: str) -> str:
        match = re.search(r"\b(CME|NYSE|NASDAQ|CBOT)\b", message, re.I)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _extract_side(message: str) -> str:
        lowered = message.lower()
        if any(kw in lowered for kw in ("buy", "achète", "achete", "acheter", "long")):
            return "buy"
        if any(kw in lowered for kw in ("sell", "vends", "vendre", "short")):
            return "sell"
        return ""

    @staticmethod
    def _extract_quantity(message: str) -> float:
        match = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:contrats?|contracts?|lots?)?\b",
            message,
            re.I,
        )
        if match:
            return float(match.group(1))
        return 0.0

    @staticmethod
    def _extract_alert_payload(message: str) -> str:
        """Extract embedded JSON or alert text from a user message."""
        json_match = re.search(r"(\{.*\})", message, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        if ":" in message and any(
            token in message.lower()
            for token in ("buy", "sell", "long", "short", "nq", "es")
        ):
            colon_idx = message.index(":")
            return message[colon_idx - 50 :].strip() if colon_idx > 50 else message.strip()
        return ""

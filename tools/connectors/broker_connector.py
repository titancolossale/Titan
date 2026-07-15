# =====================================
# Titan Broker Connector
# =====================================

"""Broker execution connector with permission gating (Phase 16.3).

Architecture:
    TradingSignal → TradingConnector → BrokerConnector → BrokerProvider

No Apex, Rithmic, Tradovate, or NinjaTrader integrations in this phase.
"""

from __future__ import annotations

from tools.connectors.base_connector import ConnectorResult
from tools.connectors.broker_models import BrokerAccount, BrokerOrder, BrokerPosition, BrokerResult
from tools.connectors.broker_provider_factory import (
    broker_provider_label,
    create_broker_provider,
)
from tools.connectors.broker_provider_protocol import BrokerProvider
from tools.connectors.broker_readiness import is_read_only_provider
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.signal_to_order import draft_order_from_signal, signal_from_params
from tools.connectors.trading_permissions import (
    TRADING_SUPPORTED_ACTIONS,
    TradingPermissionLevel,
    evaluate_trading_permission,
    is_confirmed,
    normalize_trading_action,
)

_READ_ACTIONS = frozenset({
    "list_accounts",
    "account_status",
    "get_positions",
    "get_orders",
    "get_balance",
    "get_market_status",
    "get_pnl",
    "get_margin",
    "draft_order_from_signal",
})

_WRITE_ACTIONS = frozenset({
    "place_order",
    "modify_order",
    "cancel_order",
    "flatten_position",
    "execute_signal_order",
})

_SUPPORTED_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS


def _coerce_broker_order(order: object) -> BrokerOrder:
    """Normalize provider order records to BrokerOrder."""
    if isinstance(order, BrokerOrder):
        return order
    return BrokerOrder(
        order_id=getattr(order, "order_id", ""),
        account_id=getattr(order, "account_id", ""),
        symbol=getattr(order, "symbol", ""),
        market=getattr(order, "market", "CME"),
        side=getattr(order, "side", ""),
        order_type=getattr(order, "order_type", "market"),
        quantity=float(getattr(order, "quantity", 0) or 0),
        entry_price=getattr(order, "entry_price", None) or getattr(order, "price", None),
        stop_loss=getattr(order, "stop_loss", None),
        take_profit=getattr(order, "take_profit", None),
        status=getattr(order, "status", "pending"),
        timestamp=getattr(order, "timestamp", ""),
        source_signal_id=getattr(order, "source_signal_id", ""),
        warnings=tuple(getattr(order, "warnings", ()) or ()),
    )


def _coerce_broker_account(account: object) -> BrokerAccount:
    if isinstance(account, BrokerAccount):
        return account
    return BrokerAccount(
        account_id=getattr(account, "account_id", ""),
        account_name=getattr(account, "account_name", ""),
        provider=getattr(account, "provider", "paper"),
        balance=float(getattr(account, "balance", 0) or 0),
        margin=float(getattr(account, "margin", 0) or 0),
        status=getattr(account, "status", "active"),
        market=getattr(account, "market", "CME"),
    )


def _coerce_broker_position(position: object) -> BrokerPosition:
    if isinstance(position, BrokerPosition):
        return position
    return BrokerPosition(
        symbol=getattr(position, "symbol", ""),
        side=getattr(position, "side", "flat"),
        quantity=float(getattr(position, "quantity", 0) or 0),
        average_price=float(getattr(position, "average_price", 0) or 0),
        unrealized_pnl=float(getattr(position, "unrealized_pnl", 0) or 0),
        market=getattr(position, "market", "CME"),
        account_id=getattr(position, "account_id", ""),
    )


class BrokerConnector:
    """Operate on broker accounts via a pluggable provider with permission gating."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        provider: BrokerProvider | PaperBrokerProvider | None = None,
        provider_name: str | None = None,
        mode: str | None = None,
        live_enabled: bool | None = None,
    ) -> None:
        self._enabled = enabled
        self._provider_name = provider_name
        self._mode = mode
        self._live_enabled = live_enabled
        if provider is None:
            provider = create_broker_provider(
                provider=provider_name,
                mode=mode,
                live_enabled=live_enabled,
            )
        self._provider = provider
        self._provider_label = broker_provider_label(provider)
        self._default_account_id = "paper-nq-001"
        self._default_market = "CME"

    @property
    def connector_id(self) -> str:
        return "broker"

    @property
    def backend(self) -> BrokerProvider:
        return self._provider

    @property
    def provider_label(self) -> str:
        return self._provider_label

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the broker provider with permission checks."""
        normalized = normalize_trading_action(action)
        if normalized == "signal_to_order":
            normalized = "draft_order_from_signal"
        if normalized not in self.supported_actions():
            if normalized in TRADING_SUPPORTED_ACTIONS - _SUPPORTED_ACTIONS:
                return ConnectorResult(
                    success=False,
                    action=action,
                    error=f"Action bloquée ou non implémentée : {action!r}",
                )
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action broker non supportée : {action!r}",
            )
        if not self._enabled:
            return ConnectorResult(
                success=False,
                action=normalized,
                error="Connecteur broker désactivé.",
            )

        permission = evaluate_trading_permission(
            normalized,
            params,
            confirmed=is_confirmed(params),
        )
        if permission.level == TradingPermissionLevel.BLOCKED:
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        if normalized in _WRITE_ACTIONS and self._writes_blocked():
            return ConnectorResult(
                success=False,
                action=normalized,
                error=(
                    f"Action {normalized!r} bloquée — provider "
                    f"{self._provider_label!r} en lecture seule (Phase 16.4). "
                    "Aucun ordre réel ne sera exécuté, même avec confirmed=true."
                ),
            )
        if (
            permission.level == TradingPermissionLevel.CONFIRMATION_REQUIRED
            and normalized in _WRITE_ACTIONS
        ):
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        return self._execute_action(normalized, params)

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        dispatch = {
            "list_accounts": self._list_accounts,
            "account_status": self._account_status,
            "get_positions": self._get_positions,
            "get_orders": self._get_orders,
            "get_balance": self._get_balance,
            "get_market_status": self._get_market_status,
            "get_pnl": self._get_pnl,
            "get_margin": self._get_margin,
            "draft_order_from_signal": self._draft_order_from_signal,
            "place_order": self._place_order,
            "modify_order": self._modify_order,
            "cancel_order": self._cancel_order,
            "flatten_position": self._flatten_position,
            "execute_signal_order": self._execute_signal_order,
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

    def _list_accounts(self, params: dict) -> ConnectorResult:
        accounts = [
            _coerce_broker_account(account)
            for account in self._provider.list_accounts()
        ]
        result = BrokerResult(
            provider=self._provider_label,
            status="ok",
            accounts=tuple(accounts),
            warnings=self._provider_warning(),
        )
        return self._success("list_accounts", result)

    def _account_status(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        account = self._provider.account_status(account_id)
        if account is None:
            return ConnectorResult(
                success=False,
                action="account_status",
                error=f"Compte introuvable : {account_id!r}",
            )
        coerced = _coerce_broker_account(account)
        result = BrokerResult(
            provider=coerced.provider,
            account_id=coerced.account_id,
            account_name=coerced.account_name,
            market=coerced.market,
            balance=coerced.balance,
            margin=coerced.margin,
            status=coerced.status,
            warnings=self._provider_warning(),
        )
        return self._success("account_status", result, target_path=account_id)

    def _get_positions(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip() or None
        positions = [
            _coerce_broker_position(position)
            for position in self._provider.get_positions(account_id, symbol=symbol)
        ]
        account = self._provider.account_status(account_id)
        primary = positions[0] if positions else None
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            market=primary.market if primary else self._default_market,
            symbol=primary.symbol if primary else (symbol or ""),
            positions=tuple(positions),
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_positions", result, target_path=account_id)

    def _get_orders(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip() or None
        status = str(params.get("status", "")).strip() or None
        orders = [
            _coerce_broker_order(order)
            for order in self._provider.get_orders(
                account_id,
                symbol=symbol,
                status=status,
            )
        ]
        account = self._provider.account_status(account_id)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            symbol=symbol or "",
            orders=tuple(orders),
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_orders", result, target_path=account_id)

    def _get_balance(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        balance, margin = self._provider.get_balance(account_id)
        account = self._provider.account_status(account_id)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            balance=balance,
            margin=margin,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_balance", result, target_path=account_id)

    def _get_market_status(self, params: dict) -> ConnectorResult:
        market = str(params.get("market", self._default_market)).strip()
        status = self._provider.get_market_status(market)
        result = BrokerResult(
            provider=self._provider_label,
            market=market,
            status=status,
            warnings=self._provider_warning(),
        )
        return self._success("get_market_status", result, target_path=market)

    def _get_pnl(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        pnl = self._provider.get_pnl(account_id)
        account = self._provider.account_status(account_id)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            pnl=pnl,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_pnl", result, target_path=account_id)

    def _get_margin(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        margin = self._provider.get_margin(account_id)
        account = self._provider.account_status(account_id)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            margin=margin,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_margin", result, target_path=account_id)

    def _draft_order_from_signal(self, params: dict) -> ConnectorResult:
        signal = signal_from_params(params)
        account_id = self._resolve_account_id(params)
        draft = draft_order_from_signal(
            signal,
            account_id=account_id,
            default_market=self._default_market,
        )
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            symbol=draft.symbol,
            market=draft.market,
            status="draft",
            draft_order=draft,
            warnings=draft.warnings + self._provider_warning(),
        )
        return self._success("draft_order_from_signal", result, target_path=draft.symbol)

    def _place_order(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip().upper()
        side = str(params.get("side", "")).strip().lower()
        quantity_raw = params.get("quantity", params.get("qty"))
        if not symbol or not side:
            return ConnectorResult(
                success=False,
                action="place_order",
                error="Paramètres symbol et side requis.",
            )
        if quantity_raw is None:
            return ConnectorResult(
                success=False,
                action="place_order",
                error="Paramètre quantity requis.",
            )
        quantity = float(quantity_raw)
        order_type = str(params.get("order_type", "market")).strip().lower()
        entry_raw = params.get("entry_price", params.get("price"))
        entry_price = float(entry_raw) if entry_raw is not None else None
        stop_raw = params.get("stop_loss")
        stop_loss = float(stop_raw) if stop_raw is not None else None
        take_raw = params.get("take_profit")
        take_profit = float(take_raw) if take_raw is not None else None
        market = str(params.get("market", self._default_market)).strip()
        source_signal_id = str(
            params.get("source_signal_id", params.get("alert_id", "")),
        ).strip()
        order = _coerce_broker_order(
            self._provider.place_order(
                account_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                market=market,
                source_signal_id=source_signal_id,
            ),
        )
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            market=order.market,
            symbol=order.symbol,
            order_id=order.order_id,
            status=order.status,
            order=order,
            orders=(order,),
            warnings=self._provider_warning(),
        )
        return self._success("place_order", result, target_path=order.order_id)

    def _modify_order(self, params: dict) -> ConnectorResult:
        order_id = str(params.get("order_id", "")).strip()
        if not order_id:
            return ConnectorResult(
                success=False,
                action="modify_order",
                error="Paramètre order_id requis.",
            )
        quantity_raw = params.get("quantity")
        entry_raw = params.get("entry_price", params.get("price"))
        stop_raw = params.get("stop_loss")
        take_raw = params.get("take_profit")
        quantity = float(quantity_raw) if quantity_raw is not None else None
        entry_price = float(entry_raw) if entry_raw is not None else None
        stop_loss = float(stop_raw) if stop_raw is not None else None
        take_profit = float(take_raw) if take_raw is not None else None
        order = self._provider.modify_order(
            order_id,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if order is None:
            return ConnectorResult(
                success=False,
                action="modify_order",
                error=f"Ordre introuvable : {order_id!r}",
            )
        coerced = _coerce_broker_order(order)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=coerced.account_id,
            market=coerced.market,
            symbol=coerced.symbol,
            order_id=coerced.order_id,
            status=coerced.status,
            order=coerced,
            orders=(coerced,),
            warnings=self._provider_warning(),
        )
        return self._success("modify_order", result, target_path=order_id)

    def _cancel_order(self, params: dict) -> ConnectorResult:
        order_id = str(params.get("order_id", "")).strip()
        if not order_id:
            return ConnectorResult(
                success=False,
                action="cancel_order",
                error="Paramètre order_id requis.",
            )
        cancelled = self._provider.cancel_order(order_id)
        if not cancelled:
            return ConnectorResult(
                success=False,
                action="cancel_order",
                error=f"Ordre introuvable : {order_id!r}",
            )
        result = BrokerResult(
            provider=self._provider_label,
            order_id=order_id,
            status="cancelled",
            warnings=self._provider_warning(),
        )
        return self._success("cancel_order", result, target_path=order_id)

    def _flatten_position(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip().upper()
        if not symbol:
            return ConnectorResult(
                success=False,
                action="flatten_position",
                error="Paramètre symbol requis.",
            )
        market = str(params.get("market", self._default_market)).strip()
        source_signal_id = str(
            params.get("source_signal_id", params.get("alert_id", "")),
        ).strip()
        order = self._provider.flatten_position(
            account_id,
            symbol=symbol,
            market=market,
            source_signal_id=source_signal_id,
        )
        if order is None:
            return ConnectorResult(
                success=False,
                action="flatten_position",
                error=f"Aucune position ouverte pour {symbol!r}.",
            )
        coerced = _coerce_broker_order(order)
        result = BrokerResult(
            provider=self._provider_label,
            account_id=account_id,
            market=coerced.market,
            symbol=coerced.symbol,
            order_id=coerced.order_id,
            status=coerced.status,
            order=coerced,
            orders=(coerced,),
            warnings=self._provider_warning(),
        )
        return self._success("flatten_position", result, target_path=order.order_id)

    def _execute_signal_order(self, params: dict) -> ConnectorResult:
        """Place an order from a TradingSignal — requires confirmed=true."""
        signal = signal_from_params(params)
        account_id = self._resolve_account_id(params)
        draft = draft_order_from_signal(
            signal,
            account_id=account_id,
            default_market=self._default_market,
        )
        if draft.side == "close":
            return self._flatten_position(
                {
                    **params,
                    "symbol": draft.symbol,
                    "market": draft.market,
                    "account_id": account_id,
                    "confirmed": True,
                },
            )
        place_params = {
            "account_id": account_id,
            "symbol": draft.symbol,
            "side": draft.side,
            "quantity": draft.quantity,
            "order_type": draft.order_type,
            "entry_price": draft.entry_price,
            "stop_loss": draft.stop_loss,
            "take_profit": draft.take_profit,
            "market": draft.market,
            "source_signal_id": draft.source_signal_id,
            "confirmed": True,
        }
        return self._place_order(place_params)

    def _resolve_account_id(self, params: dict) -> str:
        account_id = str(
            params.get("account_id", params.get("account", "")),
        ).strip()
        return account_id or self._default_account_id

    def _writes_blocked(self) -> bool:
        """Return True when write operations must never reach the provider."""
        return is_read_only_provider(self._provider)

    def _provider_warning(self) -> tuple[str, ...]:
        if is_read_only_provider(self._provider):
            report = getattr(self._provider, "readiness", None)
            if callable(report):
                readiness = report()
                return readiness.warnings + (
                    "Provider lecture seule — place_order, modify_order, "
                    "cancel_order et flatten_position toujours bloqués.",
                )
            return (
                "Provider lecture seule — aucune exécution d'ordre réel.",
            )
        if self._provider_label == "paper":
            return (
                "Paper broker — simulation uniquement, aucun ordre réel.",
            )
        if self._provider_label != "mock":
            return ()
        return (
            "Provider mock — paper trading simulé, aucun broker externe connecté.",
        )

    @staticmethod
    def _success(
        action: str,
        result: BrokerResult,
        *,
        target_path: str = "",
    ) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            action=action,
            data=result.to_json(),
            target_path=target_path,
        )

# =====================================
# Titan Trading Connector
# =====================================

"""Trading connector — provider-independent (Phase 16.1).

Broker integrations (Apex, Rithmic, NinjaTrader, TradingView) are injected via
provider factory in future phases; this module never imports broker APIs directly.
"""

from __future__ import annotations

import json

from tools.connectors.base_connector import ConnectorResult
from tools.connectors.broker_connector import BrokerConnector
from tools.connectors.broker_provider_factory import create_broker_provider
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.trading_models import (
    TradingAccount,
    TradingOrder,
    TradingPosition,
    TradingResult,
    TradingSessionState,
)
from tools.connectors.trading_permissions import (
    TRADING_SUPPORTED_ACTIONS,
    TradingPermissionLevel,
    evaluate_trading_permission,
    is_confirmed,
    normalize_trading_action,
)
from tools.connectors.trading_provider import MockTradingProvider
from tools.connectors.trading_provider_factory import create_trading_provider, provider_label
from tools.connectors.trading_provider_protocol import TradingProvider
from tools.connectors.trading_validator import validate_trading_config
from tools.connectors.tradingview_provider import TradingViewProvider

_READ_ACTIONS = frozenset({
    "list_accounts",
    "account_status",
    "get_positions",
    "get_orders",
    "get_price",
    "get_balance",
    "get_market_status",
    "receive_alert",
    "parse_alert",
    "validate_alert",
    "identify_strategy",
    "extract_signal",
    "list_alerts",
    "get_latest_alert",
    "draft_order_from_signal",
    "signal_to_order",
})

_WRITE_ACTIONS = frozenset({
    "place_order",
    "modify_order",
    "cancel_order",
    "flatten_position",
    "execute_signal_order",
})

# Read actions handled by BrokerConnector (excluding get_price and TradingView)
_BROKER_READ_ACTIONS = frozenset({
    "list_accounts",
    "account_status",
    "get_positions",
    "get_orders",
    "get_balance",
    "get_market_status",
    "draft_order_from_signal",
    "signal_to_order",
})

_BROKER_ACTIONS = _BROKER_READ_ACTIONS | _WRITE_ACTIONS


def _broker_order_dict_to_trading(order: dict) -> dict:
    """Map BrokerOrder dict fields to TradingOrder JSON shape."""
    return {
        "order_id": order.get("order_id", ""),
        "symbol": order.get("symbol", ""),
        "side": order.get("side", ""),
        "order_type": order.get("order_type", "market"),
        "quantity": order.get("quantity", 0),
        "price": order.get("entry_price"),
        "status": order.get("status", ""),
        "market": order.get("market", ""),
    }


_SUPPORTED_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS


class TradingConnector:
    """Operate on trading accounts via a pluggable provider with permission gating."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        provider: TradingProvider | MockTradingProvider | None = None,
        provider_name: str | None = None,
        mode: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._provider_name = provider_name
        self._mode = mode
        broker_provider: PaperBrokerProvider | None = None
        if provider is None:
            validation = validate_trading_config(
                enabled=enabled,
                timeout_seconds=timeout_seconds,
                provider=provider_name,
                mode=mode,
            )
            if validation.ok:
                provider = create_trading_provider(provider=validation.provider)
                broker_provider = create_broker_provider(
                    provider=validation.provider,
                    mode=mode,
                )
            else:
                provider = MockTradingProvider()
                broker_provider = provider
        elif isinstance(provider, PaperBrokerProvider):
            broker_provider = provider
        self._provider = provider
        self._provider_label = provider_label(provider)
        if broker_provider is None:
            broker_provider = create_broker_provider(
                provider=provider_name,
                mode=mode,
            )
        self._broker = BrokerConnector(
            enabled=enabled,
            provider=broker_provider,
            provider_name=provider_name,
            mode=mode,
        )
        self._session = TradingSessionState()
        self._alert_backend: TradingViewProvider | None = None

    def _tradingview_backend(self) -> TradingViewProvider:
        """Return TradingView backend for alert operations."""
        if isinstance(self._provider, TradingViewProvider):
            return self._provider
        if self._alert_backend is None:
            self._alert_backend = TradingViewProvider()
        return self._alert_backend

    @property
    def connector_id(self) -> str:
        return "trading"

    @property
    def broker(self) -> BrokerConnector:
        return self._broker

    @property
    def backend(self) -> TradingProvider:
        return self._provider

    @property
    def is_configured(self) -> bool:
        if not self._enabled:
            return False
        effective_provider = (
            "mock" if self._provider_label == "mock" else (self._provider_name or None)
        )
        validation = validate_trading_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
            mode=self._mode,
        )
        return validation.ok

    @property
    def session(self) -> TradingSessionState:
        return self._session

    def configuration_error(self) -> str:
        """Return a French error when the connector is not ready."""
        effective_provider = (
            "mock" if self._provider_label == "mock" else (self._provider_name or None)
        )
        result = validate_trading_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
            mode=self._mode,
        )
        return result.message

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        validation = validate_trading_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=self._provider_name,
            mode=self._mode,
        )
        if not validation.ok:
            return False, validation.message
        self._session.started = True
        try:
            account_count = len(self._provider.list_accounts())
        except Exception as exc:
            return False, f"Échec de connexion au provider trading : {exc}"
        return True, (
            f"{validation.message} Provider {self._provider_label} : "
            f"{account_count} compte(s) accessible(s)."
        )

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the connector implementation."""
        normalized = normalize_trading_action(action)
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
                error=f"Action non supportée : {action!r}",
            )
        if not self.is_configured:
            return ConnectorResult(
                success=False,
                action=action,
                error=self.configuration_error(),
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
        if (
            permission.level == TradingPermissionLevel.CONFIRMATION_REQUIRED
            and normalized in _WRITE_ACTIONS
        ):
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        self._session.started = True
        if normalized in _BROKER_ACTIONS:
            return self._execute_broker_action(normalized, params)
        return self._execute_action(normalized, params)

    def _execute_broker_action(self, action: str, params: dict) -> ConnectorResult:
        """Delegate broker read/write operations to BrokerConnector."""
        outcome = self._broker.execute(action, params)
        if not outcome.success:
            return outcome
        return ConnectorResult(
            success=True,
            action=outcome.action,
            data=self._broker_json_to_trading_json(outcome.data),
            target_path=outcome.target_path,
        )

    @staticmethod
    def _broker_json_to_trading_json(broker_json: str) -> str:
        """Map BrokerResult JSON to TradingResult JSON for backward compatibility."""
        payload = json.loads(broker_json)
        trading_payload = {
            "provider": payload.get("provider", "paper"),
            "account_name": payload.get("account_name", ""),
            "account_id": payload.get("account_id", ""),
            "market": payload.get("market", ""),
            "symbol": payload.get("symbol", ""),
            "timeframe": "",
            "bid": None,
            "ask": None,
            "last_price": None,
            "position": payload["positions"][0] if payload.get("positions") else None,
            "pnl": None,
            "balance": payload.get("balance"),
            "margin": payload.get("margin"),
            "status": payload.get("status", "ok"),
            "warnings": payload.get("warnings", []),
            "accounts": payload.get("accounts", []),
            "positions": payload.get("positions", []),
            "orders": [
                _broker_order_dict_to_trading(o)
                for o in payload.get("orders", [])
            ],
            "order_id": payload.get("order_id", ""),
            "signal": None,
            "signals": [],
            "validation": None,
            "parsed_alert": None,
            "strategy_name": "",
            "draft_order": payload.get("draft_order"),
        }
        order = payload.get("order")
        if order and not trading_payload["orders"]:
            trading_payload["orders"] = [
                _broker_order_dict_to_trading(order),
            ]
        if payload.get("draft_order"):
            trading_payload["draft_order"] = payload["draft_order"]
        return json.dumps(trading_payload, ensure_ascii=False, indent=2)

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        dispatch = {
            "list_accounts": self._list_accounts,
            "account_status": self._account_status,
            "get_positions": self._get_positions,
            "get_orders": self._get_orders,
            "get_price": self._get_price,
            "get_balance": self._get_balance,
            "get_market_status": self._get_market_status,
            "place_order": self._place_order,
            "modify_order": self._modify_order,
            "cancel_order": self._cancel_order,
            "flatten_position": self._flatten_position,
            "receive_alert": self._receive_alert,
            "parse_alert": self._parse_alert,
            "validate_alert": self._validate_alert,
            "identify_strategy": self._identify_strategy,
            "extract_signal": self._extract_signal,
            "list_alerts": self._list_alerts,
            "get_latest_alert": self._get_latest_alert,
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
        accounts = self._provider.list_accounts()
        result = TradingResult(
            provider=self._provider_label,
            status="ok",
            accounts=tuple(self._to_account_model(account) for account in accounts),
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
        model = self._to_account_model(account)
        result = TradingResult(
            provider=model.provider,
            account_name=model.account_name,
            account_id=model.account_id,
            market=account.market,
            balance=model.balance,
            margin=model.margin,
            status=model.status,
            warnings=self._provider_warning(),
        )
        return self._success("account_status", result, target_path=account_id)

    def _get_positions(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip() or None
        positions = self._provider.get_positions(account_id, symbol=symbol)
        account = self._provider.account_status(account_id)
        total_pnl = sum(p.unrealized_pnl for p in positions)
        primary = positions[0] if positions else None
        result = TradingResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            market=primary.market if primary else self._session.default_market,
            symbol=primary.symbol if primary else (symbol or ""),
            position=self._to_position_model(primary) if primary else None,
            pnl=total_pnl if positions else 0.0,
            positions=tuple(self._to_position_model(p) for p in positions),
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_positions", result, target_path=account_id)

    def _get_orders(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        symbol = str(params.get("symbol", "")).strip() or None
        status = str(params.get("status", "")).strip() or None
        orders = self._provider.get_orders(
            account_id,
            symbol=symbol,
            status=status,
        )
        account = self._provider.account_status(account_id)
        result = TradingResult(
            provider=self._provider_label,
            account_id=account_id,
            account_name=account.account_name if account else "",
            symbol=symbol or "",
            orders=tuple(self._to_order_model(order) for order in orders),
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_orders", result, target_path=account_id)

    def _get_price(self, params: dict) -> ConnectorResult:
        symbol = str(params.get("symbol", "NQ")).strip().upper()
        market = str(params.get("market", self._session.default_market)).strip()
        timeframe = str(params.get("timeframe", "1m")).strip()
        quote = self._provider.get_price(symbol, market=market, timeframe=timeframe)
        if quote is None:
            return ConnectorResult(
                success=False,
                action="get_price",
                error=f"Cotation introuvable : {symbol!r}",
            )
        result = TradingResult(
            provider=self._provider_label,
            market=quote.market,
            symbol=quote.symbol,
            timeframe=quote.timeframe,
            bid=quote.bid,
            ask=quote.ask,
            last_price=quote.last_price,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("get_price", result, target_path=symbol)

    def _get_balance(self, params: dict) -> ConnectorResult:
        account_id = self._resolve_account_id(params)
        balance, margin = self._provider.get_balance(account_id)
        account = self._provider.account_status(account_id)
        result = TradingResult(
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
        market = str(params.get("market", self._session.default_market)).strip()
        status = self._provider.get_market_status(market)
        result = TradingResult(
            provider=self._provider_label,
            market=market,
            status=status,
            warnings=self._provider_warning(),
        )
        return self._success("get_market_status", result, target_path=market)

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
        price_raw = params.get("price")
        price = float(price_raw) if price_raw is not None else None
        market = str(params.get("market", self._session.default_market)).strip()
        order = self._provider.place_order(
            account_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            market=market,
        )
        result = TradingResult(
            provider=self._provider_label,
            account_id=account_id,
            market=order.market,
            symbol=order.symbol,
            order_id=order.order_id,
            status=order.status,
            warnings=self._provider_warning(),
            orders=(self._to_order_model(order),),
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
        price_raw = params.get("price")
        quantity = float(quantity_raw) if quantity_raw is not None else None
        price = float(price_raw) if price_raw is not None else None
        order = self._provider.modify_order(
            order_id,
            quantity=quantity,
            price=price,
        )
        if order is None:
            return ConnectorResult(
                success=False,
                action="modify_order",
                error=f"Ordre introuvable : {order_id!r}",
            )
        result = TradingResult(
            provider=self._provider_label,
            account_id=order.account_id,
            market=order.market,
            symbol=order.symbol,
            order_id=order.order_id,
            status=order.status,
            warnings=self._provider_warning(),
            orders=(self._to_order_model(order),),
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
        result = TradingResult(
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
        market = str(params.get("market", self._session.default_market)).strip()
        order = self._provider.flatten_position(
            account_id,
            symbol=symbol,
            market=market,
        )
        if order is None:
            return ConnectorResult(
                success=False,
                action="flatten_position",
                error=f"Aucune position ouverte pour {symbol!r}.",
            )
        result = TradingResult(
            provider=self._provider_label,
            account_id=account_id,
            market=order.market,
            symbol=order.symbol,
            order_id=order.order_id,
            status=order.status,
            warnings=self._provider_warning(),
            orders=(self._to_order_model(order),),
        )
        return self._success("flatten_position", result, target_path=order.order_id)

    def _receive_alert(self, params: dict) -> ConnectorResult:
        payload = self._resolve_alert_payload(params)
        headers = self._resolve_alert_headers(params)
        secret = str(params.get("webhook_secret", params.get("secret", ""))).strip() or None
        backend = self._tradingview_backend()
        try:
            signal = backend.receive_alert(payload, headers=headers, secret=secret)
        except ValueError as exc:
            return ConnectorResult(
                success=False,
                action="receive_alert",
                error=str(exc),
            )
        result = TradingResult(
            provider="tradingview",
            status="ok",
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            last_price=signal.price,
            strategy_name=signal.strategy_name,
            signal=signal.to_dict(),
            warnings=self._tradingview_warning(),
        )
        return self._success("receive_alert", result, target_path=signal.alert_id)

    def _parse_alert(self, params: dict) -> ConnectorResult:
        payload = self._resolve_alert_payload(params)
        backend = self._tradingview_backend()
        parsed = backend.parse_alert(payload)
        result = TradingResult(
            provider="tradingview",
            status="ok",
            parsed_alert=parsed.to_dict(),
            strategy_name=parsed.strategy_hint,
            warnings=self._tradingview_warning(),
        )
        return self._success("parse_alert", result)

    def _validate_alert(self, params: dict) -> ConnectorResult:
        payload = self._resolve_alert_payload(params)
        headers = self._resolve_alert_headers(params)
        secret = str(params.get("webhook_secret", params.get("secret", ""))).strip() or None
        backend = self._tradingview_backend()
        validation = backend.validate_alert(payload, headers=headers, secret=secret)
        result = TradingResult(
            provider="tradingview",
            status="ok" if validation.ok else "invalid",
            validation=validation.to_dict(),
            warnings=self._tradingview_warning(),
        )
        if not validation.ok:
            return ConnectorResult(
                success=False,
                action="validate_alert",
                error=validation.message,
                data=result.to_json(),
            )
        return self._success("validate_alert", result)

    def _identify_strategy(self, params: dict) -> ConnectorResult:
        payload = self._resolve_alert_payload(params)
        backend = self._tradingview_backend()
        parsed = backend.parse_alert(payload)
        strategy_name = backend.identify_strategy(parsed)
        result = TradingResult(
            provider="tradingview",
            status="ok",
            strategy_name=strategy_name,
            parsed_alert=parsed.to_dict(),
            warnings=self._tradingview_warning(),
        )
        return self._success("identify_strategy", result, target_path=strategy_name)

    def _extract_signal(self, params: dict) -> ConnectorResult:
        payload = self._resolve_alert_payload(params)
        backend = self._tradingview_backend()
        parsed = backend.parse_alert(payload)
        strategy_name = str(params.get("strategy_name", "")).strip()
        if not strategy_name:
            strategy_name = backend.identify_strategy(parsed)
        signal = backend.extract_signal(parsed, strategy_name=strategy_name)
        result = TradingResult(
            provider="tradingview",
            status="ok",
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            last_price=signal.price,
            strategy_name=signal.strategy_name,
            signal=signal.to_dict(),
            warnings=self._tradingview_warning(),
        )
        return self._success("extract_signal", result, target_path=signal.symbol)

    def _list_alerts(self, params: dict) -> ConnectorResult:
        limit_raw = params.get("limit", 50)
        limit = int(limit_raw) if limit_raw is not None else 50
        backend = self._tradingview_backend()
        signals = backend.list_signals(limit=limit)
        result = TradingResult(
            provider="tradingview",
            status="ok",
            signals=tuple(signal.to_dict() for signal in signals),
            warnings=self._tradingview_warning(),
        )
        return self._success("list_alerts", result)

    def _get_latest_alert(self, params: dict) -> ConnectorResult:
        symbol = str(params.get("symbol", "")).strip() or None
        strategy_name = str(params.get("strategy_name", "")).strip() or None
        backend = self._tradingview_backend()
        signal = backend.get_latest_signal(symbol=symbol, strategy_name=strategy_name)
        if signal is None:
            return ConnectorResult(
                success=False,
                action="get_latest_alert",
                error="Aucune alerte TradingView enregistrée.",
            )
        result = TradingResult(
            provider="tradingview",
            status="ok",
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            last_price=signal.price,
            strategy_name=signal.strategy_name,
            signal=signal.to_dict(),
            warnings=self._tradingview_warning(),
        )
        return self._success("get_latest_alert", result, target_path=signal.alert_id)

    @staticmethod
    def _resolve_alert_payload(params: dict) -> str | dict:
        for key in ("payload", "raw_message", "message", "body", "text"):
            value = params.get(key)
            if value is not None and str(value).strip():
                if isinstance(value, dict):
                    return value
                return str(value)
        return ""

    @staticmethod
    def _resolve_alert_headers(params: dict) -> dict[str, str] | None:
        headers = params.get("headers")
        if isinstance(headers, dict):
            return {str(key): str(value) for key, value in headers.items()}
        return None

    def _tradingview_warning(self) -> tuple[str, ...]:
        if self._provider_label == "tradingview":
            return (
                "TradingView — réception d'alertes uniquement, aucun ordre exécuté.",
            )
        return (
            "Alertes TradingView via backend dédié — aucun ordre exécuté.",
        )

    def _resolve_account_id(self, params: dict) -> str:
        account_id = str(
            params.get("account_id", params.get("account", "")),
        ).strip()
        return account_id or self._session.default_account_id

    def _provider_warning(self) -> tuple[str, ...]:
        if self._provider_label != "mock":
            return ()
        return (
            "Provider mock — paper trading simulé, aucun broker externe connecté.",
        )

    @staticmethod
    def _to_account_model(account) -> TradingAccount:
        return TradingAccount(
            account_id=account.account_id,
            account_name=account.account_name,
            provider=account.provider,
            balance=account.balance,
            margin=account.margin,
            status=account.status,
        )

    @staticmethod
    def _to_position_model(position) -> TradingPosition:
        return TradingPosition(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            average_price=position.average_price,
            unrealized_pnl=position.unrealized_pnl,
            market=position.market,
        )

    @staticmethod
    def _to_order_model(order) -> TradingOrder:
        return TradingOrder(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            status=order.status,
            market=order.market,
        )

    @staticmethod
    def _success(
        action: str,
        result: TradingResult,
        *,
        target_path: str = "",
    ) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            action=action,
            data=result.to_json(),
            target_path=target_path,
        )

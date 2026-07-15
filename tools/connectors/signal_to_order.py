# =====================================
# Titan Signal to Order Conversion
# =====================================

"""Convert TradingSignal into BrokerOrder drafts (Phase 16.3)."""

from __future__ import annotations

from tools.connectors.broker_models import BrokerOrder
from tools.connectors.tradingview_models import TradingSignal

_ACTION_TO_SIDE = {
    "buy": "buy",
    "sell": "sell",
    "long": "buy",
    "short": "sell",
    "close": "close",
    "exit": "close",
    "flat": "close",
}


def draft_order_from_signal(
    signal: TradingSignal,
    *,
    account_id: str = "paper-nq-001",
    default_market: str = "CME",
) -> BrokerOrder:
    """Convert a TradingSignal into a BrokerOrder draft without executing."""
    action = signal.action.strip().lower()
    side = _ACTION_TO_SIDE.get(action, action)
    quantity = signal.contracts if signal.contracts > 0 else 1.0
    order_type = "limit" if signal.price is not None else "market"
    warnings: list[str] = [
        "Brouillon d'ordre — aucune exécution sans confirmed=true.",
    ]

    if action in {"close", "exit", "flat"}:
        warnings.append(
            "Signal de clôture — préférer flatten_position pour fermer une position.",
        )
        side = "close"

    if not signal.symbol:
        warnings.append("Symbole manquant dans le signal.")

    if not action:
        warnings.append("Action manquante dans le signal.")

    return BrokerOrder(
        order_id="",
        account_id=account_id,
        symbol=signal.symbol.upper() if signal.symbol else "",
        market=signal.market or default_market,
        side=side,
        order_type=order_type,
        quantity=quantity,
        entry_price=signal.price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        status="draft",
        source_signal_id=signal.alert_id,
        warnings=tuple(warnings),
    )


def signal_from_params(params: dict) -> TradingSignal:
    """Build TradingSignal from connector/tool params or nested signal dict."""
    nested = params.get("signal")
    if isinstance(nested, dict):
        return TradingSignal(
            strategy_name=str(nested.get("strategy_name", "")),
            symbol=str(nested.get("symbol", "")),
            market=str(nested.get("market", "")),
            timeframe=str(nested.get("timeframe", "")),
            action=str(nested.get("action", "")),
            contracts=float(nested.get("contracts", 0) or 0),
            price=nested.get("price"),
            stop_loss=nested.get("stop_loss"),
            take_profit=nested.get("take_profit"),
            timestamp=str(nested.get("timestamp", "")),
            alert_id=str(nested.get("alert_id", "")),
            raw_message=str(nested.get("raw_message", "")),
            payload_format=str(nested.get("payload_format", "")),
        )
    return TradingSignal(
        strategy_name=str(params.get("strategy_name", "")),
        symbol=str(params.get("symbol", "")),
        market=str(params.get("market", "")),
        timeframe=str(params.get("timeframe", "")),
        action=str(params.get("action", "")),
        contracts=float(params.get("contracts", params.get("quantity", 0)) or 0),
        price=params.get("price", params.get("entry_price")),
        stop_loss=params.get("stop_loss"),
        take_profit=params.get("take_profit"),
        timestamp=str(params.get("timestamp", "")),
        alert_id=str(params.get("alert_id", params.get("source_signal_id", ""))),
        raw_message=str(params.get("raw_message", "")),
        payload_format=str(params.get("payload_format", "")),
    )

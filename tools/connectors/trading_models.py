# =====================================
# Titan Trading Models
# =====================================

"""Structured trading results for the Trading connector (Phase 16.1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TradingPosition:
    """An open trading position."""

    symbol: str
    side: str = "flat"
    quantity: float = 0.0
    average_price: float = 0.0
    unrealized_pnl: float = 0.0
    market: str = ""


@dataclass(frozen=True)
class TradingOrder:
    """A trading order record."""

    order_id: str
    symbol: str
    side: str = ""
    order_type: str = "market"
    quantity: float = 0.0
    price: float | None = None
    status: str = "pending"
    market: str = ""


@dataclass(frozen=True)
class TradingAccount:
    """A trading account summary."""

    account_id: str
    account_name: str
    provider: str = "mock"
    balance: float = 0.0
    margin: float = 0.0
    status: str = "active"


@dataclass(frozen=True)
class TradingResult:
    """Structured outcome from a Trading connector operation."""

    provider: str = "mock"
    account_name: str = ""
    account_id: str = ""
    market: str = ""
    symbol: str = ""
    timeframe: str = ""
    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None
    position: TradingPosition | None = None
    pnl: float | None = None
    balance: float | None = None
    margin: float | None = None
    status: str = "ok"
    warnings: tuple[str, ...] = ()
    accounts: tuple[TradingAccount, ...] = ()
    positions: tuple[TradingPosition, ...] = ()
    orders: tuple[TradingOrder, ...] = ()
    order_id: str = ""
    signal: dict | None = None
    signals: tuple[dict, ...] = ()
    validation: dict | None = None
    parsed_alert: dict | None = None
    strategy_name: str = ""

    def to_json(self) -> str:
        """Serialize for ToolResult.data and logging."""
        payload = {
            "provider": self.provider,
            "account_name": self.account_name,
            "account_id": self.account_id,
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bid": self.bid,
            "ask": self.ask,
            "last_price": self.last_price,
            "position": asdict(self.position) if self.position else None,
            "pnl": self.pnl,
            "balance": self.balance,
            "margin": self.margin,
            "status": self.status,
            "warnings": list(self.warnings),
            "accounts": [asdict(account) for account in self.accounts],
            "positions": [asdict(pos) for pos in self.positions],
            "orders": [asdict(order) for order in self.orders],
            "order_id": self.order_id,
            "signal": self.signal,
            "signals": list(self.signals),
            "validation": self.validation,
            "parsed_alert": self.parsed_alert,
            "strategy_name": self.strategy_name,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [f"Statut : {self.status}"]
        if self.provider:
            lines.append(f"Provider : {self.provider}")
        if self.account_name:
            lines.append(f"Compte : {self.account_name} ({self.account_id})")
        if self.market:
            lines.append(f"Marché : {self.market}")
        if self.symbol:
            lines.append(f"Symbole : {self.symbol}")
        if self.timeframe:
            lines.append(f"Timeframe : {self.timeframe}")
        if self.last_price is not None:
            lines.append(f"Dernier prix : {self.last_price}")
        if self.bid is not None and self.ask is not None:
            lines.append(f"Bid/Ask : {self.bid} / {self.ask}")
        if self.balance is not None:
            lines.append(f"Solde : {self.balance}")
        if self.margin is not None:
            lines.append(f"Marge : {self.margin}")
        if self.pnl is not None:
            lines.append(f"PnL : {self.pnl}")
        if self.position is not None:
            lines.append(
                f"Position : {self.position.side} {self.position.quantity} "
                f"{self.position.symbol} @ {self.position.average_price}",
            )
        if self.accounts:
            lines.append(f"Comptes : {len(self.accounts)}")
        if self.positions:
            lines.append(f"Positions ouvertes : {len(self.positions)}")
        if self.orders:
            lines.append(f"Ordres : {len(self.orders)}")
        if self.order_id:
            lines.append(f"Ordre : {self.order_id}")
        if self.strategy_name:
            lines.append(f"Stratégie : {self.strategy_name}")
        if self.signal:
            lines.append(
                f"Signal : {self.signal.get('action', '—')} "
                f"{self.signal.get('symbol', '—')}",
            )
        if self.signals:
            lines.append(f"Alertes : {len(self.signals)}")
        if self.warnings:
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        return "\n".join(lines)


@dataclass
class TradingSessionState:
    """In-memory connector session tracking."""

    started: bool = False
    default_account_id: str = "paper-nq-001"
    default_market: str = "CME"
    warnings: list[str] = field(default_factory=list)

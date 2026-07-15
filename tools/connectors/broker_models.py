# =====================================
# Titan Broker Models
# =====================================

"""Structured broker order and result models (Phase 16.3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class BrokerOrder:
    """A broker order record with signal lineage and risk fields."""

    order_id: str
    account_id: str
    symbol: str
    market: str = "CME"
    side: str = ""
    order_type: str = "market"
    quantity: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    status: str = "draft"
    timestamp: str = ""
    source_signal_id: str = ""
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(
                self,
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            )

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "market": self.market,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status,
            "timestamp": self.timestamp,
            "source_signal_id": self.source_signal_id,
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class BrokerAccount:
    """A broker account summary."""

    account_id: str
    account_name: str
    provider: str = "paper"
    balance: float = 0.0
    margin: float = 0.0
    status: str = "active"
    market: str = "CME"


@dataclass(frozen=True)
class BrokerPnL:
    """Profit and loss summary for a broker account."""

    account_id: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "daily_pnl": self.daily_pnl,
            "total_pnl": self.total_pnl,
        }


@dataclass(frozen=True)
class BrokerReadinessReport:
    """Readiness snapshot for a broker provider (Phase 16.4)."""

    provider_name: str
    configured: bool
    credentials_present: bool
    read_only_supported: bool
    execution_supported: bool
    status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "configured": self.configured,
            "credentials_present": self.credentials_present,
            "read_only_supported": self.read_only_supported,
            "execution_supported": self.execution_supported,
            "status": self.status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class BrokerPosition:
    """An open broker position."""

    symbol: str
    side: str = "flat"
    quantity: float = 0.0
    average_price: float = 0.0
    unrealized_pnl: float = 0.0
    market: str = "CME"
    account_id: str = ""


@dataclass(frozen=True)
class BrokerResult:
    """Structured outcome from a BrokerConnector operation."""

    provider: str = "paper"
    account_id: str = ""
    account_name: str = ""
    market: str = ""
    symbol: str = ""
    status: str = "ok"
    order_id: str = ""
    order: BrokerOrder | None = None
    orders: tuple[BrokerOrder, ...] = ()
    accounts: tuple[BrokerAccount, ...] = ()
    positions: tuple[BrokerPosition, ...] = ()
    balance: float | None = None
    margin: float | None = None
    pnl: BrokerPnL | None = None
    warnings: tuple[str, ...] = ()
    draft_order: BrokerOrder | None = None

    def to_json(self) -> str:
        payload = {
            "provider": self.provider,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "market": self.market,
            "symbol": self.symbol,
            "status": self.status,
            "order_id": self.order_id,
            "order": self.order.to_dict() if self.order else None,
            "orders": [order.to_dict() for order in self.orders],
            "accounts": [asdict(account) for account in self.accounts],
            "positions": [asdict(position) for position in self.positions],
            "balance": self.balance,
            "margin": self.margin,
            "pnl": self.pnl.to_dict() if self.pnl else None,
            "warnings": list(self.warnings),
            "draft_order": self.draft_order.to_dict() if self.draft_order else None,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


@dataclass
class BrokerSessionState:
    """In-memory broker connector session tracking."""

    started: bool = False
    default_account_id: str = "paper-nq-001"
    default_market: str = "CME"
    warnings: list[str] = field(default_factory=list)

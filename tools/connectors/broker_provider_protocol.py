# =====================================
# Titan Broker Provider Protocol
# =====================================

"""Provider-independent broker execution contract (Phase 16.3)."""

from __future__ import annotations

from typing import Protocol

from tools.connectors.broker_models import BrokerAccount, BrokerOrder, BrokerPnL, BrokerPosition


class BrokerProvider(Protocol):
    """Broker interface consumed by BrokerConnector — no live broker SDK imports here."""

    provider_name: str

    def list_accounts(self) -> list[BrokerAccount]: ...

    def account_status(self, account_id: str) -> BrokerAccount | None: ...

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[BrokerPosition]: ...

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[BrokerOrder]: ...

    def get_balance(self, account_id: str) -> tuple[float, float]: ...

    def get_market_status(self, market: str) -> str: ...

    def get_pnl(self, account_id: str) -> BrokerPnL: ...

    def get_margin(self, account_id: str) -> float: ...

    def place_order(
        self,
        account_id: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> BrokerOrder: ...

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder | None: ...

    def cancel_order(self, order_id: str) -> bool: ...

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> BrokerOrder | None: ...

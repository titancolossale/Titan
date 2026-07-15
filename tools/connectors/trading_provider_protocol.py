# =====================================
# Titan Trading Provider Protocol
# =====================================

"""Provider-independent trading backend contract (Phase 16.1)."""

from __future__ import annotations

from typing import Protocol

from tools.connectors.trading_provider import (
    StoredAccount,
    StoredOrder,
    StoredPosition,
    StoredQuote,
)


class TradingProvider(Protocol):
    """Provider interface consumed by TradingConnector — no broker SDK imports here."""

    provider_name: str

    def list_accounts(self) -> list[StoredAccount]: ...

    def account_status(self, account_id: str) -> StoredAccount | None: ...

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[StoredPosition]: ...

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[StoredOrder]: ...

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        timeframe: str | None = None,
    ) -> StoredQuote | None: ...

    def get_balance(self, account_id: str) -> tuple[float, float]: ...

    def get_market_status(self, market: str) -> str: ...

    def place_order(
        self,
        account_id: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        market: str | None = None,
    ) -> StoredOrder: ...

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        price: float | None = None,
    ) -> StoredOrder | None: ...

    def cancel_order(self, order_id: str) -> bool: ...

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
    ) -> StoredOrder | None: ...

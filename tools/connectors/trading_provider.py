# =====================================
# Titan Trading Provider (Mock)
# =====================================

"""Legacy TradingProvider adapter over PaperBrokerProvider (Phase 16.1 / 16.3)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.connectors.paper_broker_provider import PaperBrokerProvider


@dataclass
class StoredAccount:
    """Internal account record (TradingProvider protocol)."""

    account_id: str
    account_name: str
    provider: str = "mock"
    balance: float = 0.0
    margin: float = 0.0
    status: str = "active"
    market: str = "CME"


@dataclass
class StoredPosition:
    """Internal position record (TradingProvider protocol)."""

    symbol: str
    side: str = "flat"
    quantity: float = 0.0
    average_price: float = 0.0
    unrealized_pnl: float = 0.0
    market: str = "CME"
    account_id: str = ""


@dataclass
class StoredOrder:
    """Internal order record (TradingProvider protocol)."""

    order_id: str
    account_id: str
    symbol: str
    side: str = ""
    order_type: str = "market"
    quantity: float = 0.0
    price: float | None = None
    status: str = "pending"
    market: str = "CME"


@dataclass
class StoredQuote:
    """Internal quote record (TradingProvider protocol)."""

    symbol: str
    market: str = "CME"
    timeframe: str = "1m"
    bid: float = 0.0
    ask: float = 0.0
    last_price: float = 0.0


class MockTradingProvider(PaperBrokerProvider):
    """Mock paper trading adapter — wraps PaperBrokerProvider for TradingProvider protocol."""

    provider_name = "mock"

    def __init__(self) -> None:
        super().__init__()
        self.provider_name = "mock"

    def seed_defaults(self) -> None:
        super().seed_defaults()
        self.provider_name = "mock"

    def list_accounts(self) -> list[StoredAccount]:
        return [
            StoredAccount(
                account_id=account.account_id,
                account_name=account.account_name,
                provider=self.provider_name,
                balance=account.balance,
                margin=account.margin,
                status=account.status,
                market=account.market,
            )
            for account in PaperBrokerProvider.list_accounts(self)
        ]

    def account_status(self, account_id: str) -> StoredAccount | None:
        account = PaperBrokerProvider.account_status(self, account_id)
        if account is None:
            return None
        return StoredAccount(
            account_id=account.account_id,
            account_name=account.account_name,
            provider=self.provider_name,
            balance=account.balance,
            margin=account.margin,
            status=account.status,
            market=account.market,
        )

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[StoredPosition]:
        return [
            StoredPosition(
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity,
                average_price=position.average_price,
                unrealized_pnl=position.unrealized_pnl,
                market=position.market,
                account_id=position.account_id,
            )
            for position in PaperBrokerProvider.get_positions(
                self, account_id, symbol=symbol,
            )
        ]

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[StoredOrder]:
        return [
            StoredOrder(
                order_id=order.order_id,
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.entry_price,
                status=order.status,
                market=order.market,
            )
            for order in PaperBrokerProvider.get_orders(
                self, account_id, symbol=symbol, status=status,
            )
        ]

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        timeframe: str | None = None,
    ) -> StoredQuote | None:
        quote = PaperBrokerProvider.get_price(self, symbol, market=market, timeframe=timeframe)
        if quote is None:
            return None
        return StoredQuote(
            symbol=str(quote["symbol"]),
            market=str(quote.get("market", "CME")),
            timeframe=str(quote.get("timeframe", "1m")),
            bid=float(quote["bid"]),
            ask=float(quote["ask"]),
            last_price=float(quote["last_price"]),
        )

    def place_order(
        self,
        account_id: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        entry_price: float | None = None,
        market: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        source_signal_id: str = "",
    ) -> StoredOrder:
        resolved_price = entry_price if entry_price is not None else price
        order = PaperBrokerProvider.place_order(
            self,
            account_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            entry_price=resolved_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            market=market,
            source_signal_id=source_signal_id,
        )
        return StoredOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.entry_price,
            status=order.status,
            market=order.market,
        )

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        price: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> StoredOrder | None:
        resolved_price = entry_price if entry_price is not None else price
        order = PaperBrokerProvider.modify_order(
            self,
            order_id,
            quantity=quantity,
            entry_price=resolved_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if order is None:
            return None
        return StoredOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.entry_price,
            status=order.status,
            market=order.market,
        )

    def cancel_order(self, order_id: str) -> bool:
        return PaperBrokerProvider.cancel_order(self, order_id)

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> StoredOrder | None:
        order = PaperBrokerProvider.flatten_position(
            self,
            account_id,
            symbol=symbol,
            market=market,
            source_signal_id=source_signal_id,
        )
        if order is None:
            return None
        return StoredOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.entry_price,
            status=order.status,
            market=order.market,
        )

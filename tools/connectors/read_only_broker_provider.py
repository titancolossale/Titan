# =====================================
# Titan Read-Only Broker Provider
# =====================================

"""Read-only broker provider base — blocks all write operations (Phase 16.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tools.connectors.broker_models import (
    BrokerAccount,
    BrokerOrder,
    BrokerPnL,
    BrokerPosition,
    BrokerReadinessReport,
)


class BrokerWriteBlockedError(RuntimeError):
    """Raised when a write operation is attempted on a read-only broker provider."""


class ReadOnlyBrokerProvider(ABC):
    """Base for real broker integrations — read queries only, no order execution."""

    provider_name: str = "read_only"
    read_only_supported: bool = True
    execution_supported: bool = False

    @abstractmethod
    def readiness(self) -> BrokerReadinessReport:
        """Return provider readiness without connecting to live broker APIs."""

    @abstractmethod
    def list_accounts(self) -> list[BrokerAccount]: ...

    @abstractmethod
    def account_status(self, account_id: str) -> BrokerAccount | None: ...

    @abstractmethod
    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[BrokerOrder]: ...

    @abstractmethod
    def get_balance(self, account_id: str) -> tuple[float, float]: ...

    @abstractmethod
    def get_market_status(self, market: str) -> str: ...

    @abstractmethod
    def get_pnl(self, account_id: str) -> BrokerPnL: ...

    @abstractmethod
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
    ) -> BrokerOrder:
        """Always blocked — read-only providers never place orders."""
        raise BrokerWriteBlockedError(
            f"place_order bloqué — provider {self.provider_name!r} en lecture seule. "
            "Aucun ordre réel ne sera exécuté (Phase 16.4)."
        )

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder | None:
        """Always blocked — read-only providers never modify orders."""
        raise BrokerWriteBlockedError(
            f"modify_order bloqué — provider {self.provider_name!r} en lecture seule."
        )

    def cancel_order(self, order_id: str) -> bool:
        """Always blocked — read-only providers never cancel orders."""
        raise BrokerWriteBlockedError(
            f"cancel_order bloqué — provider {self.provider_name!r} en lecture seule."
        )

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> BrokerOrder | None:
        """Always blocked — read-only providers never flatten positions."""
        raise BrokerWriteBlockedError(
            f"flatten_position bloqué — provider {self.provider_name!r} en lecture seule."
        )

# =====================================
# Titan Paper Broker Provider
# =====================================

"""In-memory paper trading broker — no external broker integration (Phase 16.3)."""

from __future__ import annotations

import uuid

from tools.connectors.broker_models import BrokerAccount, BrokerOrder, BrokerPnL, BrokerPosition


class PaperBrokerProvider:
    """Paper broker execution backend — simulates fills without live capital."""

    provider_name = "paper"
    read_only_supported = False
    execution_supported = True

    def __init__(self) -> None:
        self._accounts: dict[str, BrokerAccount] = {}
        self._positions: dict[str, list[BrokerPosition]] = {}
        self._orders: dict[str, BrokerOrder] = {}
        self._quotes: dict[str, dict[str, float | str]] = {}
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """Populate default sample accounts and NQ paper data."""
        self._accounts.clear()
        self._positions.clear()
        self._orders.clear()
        self._quotes.clear()

        paper = BrokerAccount(
            account_id="paper-nq-001",
            account_name="Paper NQ — Nolan",
            provider="paper",
            balance=100_000.0,
            margin=5_000.0,
            status="active",
            market="CME",
        )
        self._accounts[paper.account_id] = paper

        ibrahim = BrokerAccount(
            account_id="paper-nq-002",
            account_name="Paper NQ — Ibrahim",
            provider="paper",
            balance=75_000.0,
            margin=3_500.0,
            status="active",
            market="CME",
        )
        self._accounts[ibrahim.account_id] = ibrahim

        self._positions[paper.account_id] = [
            BrokerPosition(
                symbol="NQ",
                side="long",
                quantity=1.0,
                average_price=18_450.25,
                unrealized_pnl=125.50,
                market="CME",
                account_id=paper.account_id,
            ),
        ]
        self._positions[ibrahim.account_id] = []

        self._quotes["NQ"] = {
            "symbol": "NQ",
            "market": "CME",
            "bid": 18_475.00,
            "ask": 18_475.50,
            "last_price": 18_475.25,
        }
        self._quotes["ES"] = {
            "symbol": "ES",
            "market": "CME",
            "bid": 5_420.25,
            "ask": 5_420.50,
            "last_price": 5_420.25,
        }

        pending = BrokerOrder(
            order_id="ord-seed-001",
            account_id=paper.account_id,
            symbol="NQ",
            market="CME",
            side="sell",
            order_type="limit",
            quantity=1.0,
            entry_price=18_500.0,
            status="working",
        )
        self._orders[pending.order_id] = pending

    def list_accounts(self) -> list[BrokerAccount]:
        return list(self._accounts.values())

    def account_status(self, account_id: str) -> BrokerAccount | None:
        return self._accounts.get(account_id)

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[BrokerPosition]:
        positions = list(self._positions.get(account_id, []))
        if symbol:
            positions = [p for p in positions if p.symbol.upper() == symbol.upper()]
        return positions

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[BrokerOrder]:
        orders = [
            order
            for order in self._orders.values()
            if order.account_id == account_id
        ]
        if symbol:
            orders = [o for o in orders if o.symbol.upper() == symbol.upper()]
        if status:
            orders = [o for o in orders if o.status == status]
        return orders

    def get_balance(self, account_id: str) -> tuple[float, float]:
        account = self._accounts.get(account_id)
        if account is None:
            raise ValueError(f"Compte introuvable : {account_id!r}")
        return account.balance, account.margin

    def get_market_status(self, market: str) -> str:
        known = {"CME", "NYSE", "NASDAQ", "CBOT"}
        if market.upper() not in known:
            return "unknown"
        return "open"

    def get_pnl(self, account_id: str) -> BrokerPnL:
        if account_id not in self._accounts:
            raise ValueError(f"Compte introuvable : {account_id!r}")
        positions = self.get_positions(account_id)
        unrealized = sum(position.unrealized_pnl for position in positions)
        return BrokerPnL(
            account_id=account_id,
            realized_pnl=0.0,
            unrealized_pnl=unrealized,
            daily_pnl=unrealized,
            total_pnl=unrealized,
        )

    def get_margin(self, account_id: str) -> float:
        _balance, margin = self.get_balance(account_id)
        return margin

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, float | str] | None:
        """Return a quote dict for *symbol* (used by TradingConnector get_price)."""
        quote = self._quotes.get(symbol.upper())
        if quote is None:
            return None
        if market and str(quote.get("market", "")).upper() != market.upper():
            return None
        resolved = dict(quote)
        if timeframe:
            resolved["timeframe"] = timeframe
        else:
            resolved["timeframe"] = "1m"
        return resolved

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
        if account_id not in self._accounts:
            raise ValueError(f"Compte introuvable : {account_id!r}")
        if quantity <= 0:
            raise ValueError("La quantité doit être positive.")
        order_id = f"ord-{uuid.uuid4().hex[:8]}"
        resolved_market = market or "CME"
        warnings: list[str] = (
            "Paper trading — aucun ordre réel exécuté.",
        )
        order = BrokerOrder(
            order_id=order_id,
            account_id=account_id,
            symbol=symbol.upper(),
            market=resolved_market,
            side=side.lower(),
            order_type=order_type.lower(),
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="submitted",
            source_signal_id=source_signal_id,
            warnings=warnings,
        )
        self._orders[order_id] = order
        if order_type.lower() == "market":
            filled = self._fill_order(order)
            self._orders[order_id] = filled
            return filled
        return order

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder | None:
        order = self._orders.get(order_id)
        if order is None:
            return None
        if order.status in {"filled", "cancelled"}:
            raise ValueError(f"Ordre non modifiable : {order_id!r} ({order.status})")
        updated = BrokerOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            market=order.market,
            side=order.side,
            order_type=order.order_type,
            quantity=quantity if quantity is not None else order.quantity,
            entry_price=entry_price if entry_price is not None else order.entry_price,
            stop_loss=stop_loss if stop_loss is not None else order.stop_loss,
            take_profit=take_profit if take_profit is not None else order.take_profit,
            status="working",
            timestamp=order.timestamp,
            source_signal_id=order.source_signal_id,
            warnings=order.warnings + ("Ordre modifié en paper trading.",),
        )
        self._orders[order_id] = updated
        return updated

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        if order.status == "filled":
            raise ValueError(f"Ordre déjà exécuté : {order_id!r}")
        cancelled = BrokerOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            market=order.market,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            status="cancelled",
            timestamp=order.timestamp,
            source_signal_id=order.source_signal_id,
            warnings=order.warnings,
        )
        self._orders[order_id] = cancelled
        return True

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> BrokerOrder | None:
        positions = self.get_positions(account_id, symbol=symbol)
        if not positions:
            return None
        position = positions[0]
        if position.quantity <= 0 or position.side == "flat":
            return None
        close_side = "sell" if position.side == "long" else "buy"
        order = self.place_order(
            account_id,
            symbol=symbol,
            side=close_side,
            quantity=position.quantity,
            order_type="market",
            market=market or position.market,
            source_signal_id=source_signal_id,
        )
        self._positions[account_id] = [
            p for p in self._positions.get(account_id, [])
            if p.symbol.upper() != symbol.upper()
        ]
        return order

    def _fill_order(self, order: BrokerOrder) -> BrokerOrder:
        quote = self._quotes.get(order.symbol.upper())
        fill_price = (
            float(quote["last_price"])
            if quote and quote.get("last_price") is not None
            else (order.entry_price or 0.0)
        )
        self._apply_fill(order.account_id, order, fill_price)
        return BrokerOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            market=order.market,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            entry_price=fill_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            status="filled",
            timestamp=order.timestamp,
            source_signal_id=order.source_signal_id,
            warnings=order.warnings,
        )

    def _apply_fill(
        self,
        account_id: str,
        order: BrokerOrder,
        fill_price: float,
    ) -> None:
        positions = self._positions.setdefault(account_id, [])
        existing = next(
            (p for p in positions if p.symbol.upper() == order.symbol.upper()),
            None,
        )
        signed_qty = order.quantity if order.side == "buy" else -order.quantity
        if existing is None:
            side = "long" if signed_qty > 0 else "short"
            positions.append(
                BrokerPosition(
                    symbol=order.symbol,
                    side=side,
                    quantity=abs(signed_qty),
                    average_price=fill_price,
                    unrealized_pnl=0.0,
                    market=order.market,
                    account_id=account_id,
                ),
            )
            return
        if existing.side == "long" and signed_qty > 0:
            total_qty = existing.quantity + signed_qty
            avg = (
                (existing.average_price * existing.quantity + fill_price * signed_qty)
                / total_qty
            )
            idx = positions.index(existing)
            positions[idx] = BrokerPosition(
                symbol=existing.symbol,
                side=existing.side,
                quantity=total_qty,
                average_price=avg,
                unrealized_pnl=existing.unrealized_pnl,
                market=existing.market,
                account_id=account_id,
            )
        elif existing.side == "short" and signed_qty < 0:
            total_qty = existing.quantity + abs(signed_qty)
            avg = (
                (
                    existing.average_price * existing.quantity
                    + fill_price * abs(signed_qty)
                )
                / total_qty
            )
            idx = positions.index(existing)
            positions[idx] = BrokerPosition(
                symbol=existing.symbol,
                side=existing.side,
                quantity=total_qty,
                average_price=avg,
                unrealized_pnl=existing.unrealized_pnl,
                market=existing.market,
                account_id=account_id,
            )
        else:
            remaining = max(0.0, existing.quantity - abs(signed_qty))
            idx = positions.index(existing)
            if remaining == 0:
                positions.pop(idx)
            else:
                positions[idx] = BrokerPosition(
                    symbol=existing.symbol,
                    side=existing.side,
                    quantity=remaining,
                    average_price=existing.average_price,
                    unrealized_pnl=existing.unrealized_pnl,
                    market=existing.market,
                    account_id=account_id,
                )

# =====================================
# Titan Trading Provider Factory
# =====================================

"""Select trading provider by configuration without leaking broker SDKs into callers."""

from __future__ import annotations

from config.settings import TITAN_TRADING_PROVIDER
from tools.connectors.broker_provider_factory import create_broker_provider
from tools.connectors.trading_provider import MockTradingProvider
from tools.connectors.trading_provider_protocol import TradingProvider
from tools.connectors.tradingview_provider import TradingViewProvider


def create_trading_provider(
    *,
    provider: str | None = None,
) -> TradingProvider:
    """Return the configured trading provider implementation."""
    resolved_provider = (provider or TITAN_TRADING_PROVIDER).strip().lower()

    if resolved_provider == "tradingview":
        return TradingViewProvider()

    if resolved_provider not in {"mock", "memory", "inmemory", "paper"}:
        raise ValueError(
            f"Provider trading inconnu : {resolved_provider!r}. "
            "Valeurs supportées : mock, paper (Phase 16.3), tradingview (Phase 16.2). "
            "Apex, Rithmic et NinjaTrader non connectés."
        )

    if resolved_provider == "paper":
        backend = create_broker_provider(provider="paper")
        return backend  # type: ignore[return-value]

    backend = MockTradingProvider()
    backend.provider_name = "mock"
    return backend


def provider_label(provider: TradingProvider) -> str:
    """Return a short provider label for connector warnings and health checks."""
    return getattr(provider, "provider_name", "mock")

# =====================================
# Titan Broker Provider Factory
# =====================================

"""Select broker provider by configuration without leaking live broker SDKs."""

from __future__ import annotations

import os

from config.settings import (
    TITAN_BROKER_PROVIDER,
    TITAN_BROKER_READ_ONLY,
    TITAN_TRADING_MODE,
    TITAN_TRADING_PROVIDER,
)
from tools.connectors.apex_rithmic_provider import (
    APEX_RITHMIC_PROVIDER_KEY,
    create_apex_rithmic_provider,
)
from tools.connectors.broker_provider_protocol import BrokerProvider
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.real_broker_stubs import (
    REAL_BROKER_PROVIDER_KEYS,
    create_real_broker_stub,
)


def create_broker_provider(
    *,
    provider: str | None = None,
    mode: str | None = None,
    live_enabled: bool | None = None,
    broker_read_only: bool | None = None,
) -> BrokerProvider:
    """Return the configured broker provider implementation."""
    resolved_provider = (
        provider or TITAN_BROKER_PROVIDER or TITAN_TRADING_PROVIDER
    ).strip().lower()
    resolved_mode = (mode or TITAN_TRADING_MODE).strip().lower()
    is_live_enabled = (
        os.getenv("TITAN_TRADING_LIVE_ENABLED", "false").lower() == "true"
        if live_enabled is None
        else live_enabled
    )
    is_broker_read_only = (
        TITAN_BROKER_READ_ONLY if broker_read_only is None else broker_read_only
    )

    if resolved_mode == "live":
        if not is_live_enabled:
            raise ValueError(
                "Mode live bloqué — TITAN_TRADING_LIVE_ENABLED=false. "
                "Utilisez TITAN_TRADING_MODE=paper."
            )
        raise ValueError(
            "Mode live non disponible en Phase 16.5 — paper ou lecture seule uniquement."
        )

    if resolved_provider == APEX_RITHMIC_PROVIDER_KEY:
        if not is_broker_read_only:
            raise ValueError(
                f"Provider broker {resolved_provider!r} bloqué — "
                "TITAN_BROKER_READ_ONLY=false. "
                "Phase 16.5 — lecture seule uniquement pour Apex/Rithmic."
            )
        return create_apex_rithmic_provider(broker_read_only=is_broker_read_only)

    if resolved_provider in REAL_BROKER_PROVIDER_KEYS:
        if not is_broker_read_only:
            raise ValueError(
                f"Provider broker {resolved_provider!r} bloqué — "
                "TITAN_BROKER_READ_ONLY=false. "
                "Phase 16.5 — lecture seule uniquement pour Apex, Rithmic, "
                "Tradovate et NinjaTrader."
            )
        return create_real_broker_stub(resolved_provider)

    if resolved_provider not in {"mock", "memory", "inmemory", "paper"}:
        raise ValueError(
            f"Provider broker inconnu : {resolved_provider!r}. "
            "Valeurs supportées : mock, paper, apex_rithmic, apex, rithmic, "
            "tradovate, ninjatrader."
        )

    backend: PaperBrokerProvider = PaperBrokerProvider()
    if resolved_provider in {"mock", "memory", "inmemory"}:
        backend.provider_name = "mock"
    return backend


def broker_provider_label(provider: BrokerProvider) -> str:
    """Return a short provider label for connector warnings and health checks."""
    return getattr(provider, "provider_name", "paper")

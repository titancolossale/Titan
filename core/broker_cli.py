# =====================================
# Titan Broker CLI
# =====================================

"""Manual broker health and readiness commands (Phase 16.4 / 16.5)."""

from __future__ import annotations

from config.settings import (
    TITAN_BROKER_PROVIDER,
    TITAN_BROKER_READ_ONLY,
    TITAN_TRADING_LIVE_ENABLED,
    TITAN_TRADING_MODE,
    TITAN_TRADING_PROVIDER,
)
from tools.connectors.broker_readiness import (
    format_broker_health_report,
    trading_safety_snapshot,
)


def run_broker_health() -> int:
    """Print broker readiness and safety configuration report."""
    active_provider = TITAN_BROKER_PROVIDER or TITAN_TRADING_PROVIDER
    print(
        format_broker_health_report(
            provider=active_provider,
            mode=TITAN_TRADING_MODE,
            live_enabled=TITAN_TRADING_LIVE_ENABLED,
            broker_read_only=TITAN_BROKER_READ_ONLY,
        ),
    )
    safety = trading_safety_snapshot()
    if safety["live_trading_enabled"]:
        print("")
        print("ÉCHEC — TITAN_TRADING_LIVE_ENABLED=true est interdit en Phase 16.5.")
        return 1
    if not safety["broker_read_only"] and active_provider.strip().lower() not in {
        "mock",
        "memory",
        "inmemory",
        "paper",
    }:
        print("")
        print(
            "ÉCHEC — provider réel sélectionné sans TITAN_BROKER_READ_ONLY=true.",
        )
        return 1
    return 0


def print_broker_cli_help() -> None:
    """Print broker CLI subcommand help."""
    print(
        "Commandes Broker :\n"
        "  python main.py broker-health  — état des providers et sécurité trading\n"
    )


def dispatch_broker_command(command: str) -> int | None:
    """Run a broker CLI subcommand; return exit code or None if unknown."""
    normalized = command.strip().lower().replace("_", "-")
    if normalized == "broker-health":
        return run_broker_health()
    if normalized in {"broker-help", "broker"}:
        print_broker_cli_help()
        return 0
    return None

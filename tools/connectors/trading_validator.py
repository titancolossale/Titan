# =====================================
# Titan Trading Validator
# =====================================

"""Production readiness validation for the Trading connector (Phase 16.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from config.settings import (
    TITAN_TRADING_MODE,
    TITAN_TRADING_PROVIDER,
    TITAN_TRADINGVIEW_ENABLED,
)


class TradingValidationCode(str, Enum):
    """Machine-readable Trading configuration status."""

    OK = "ok"
    TRADING_DISABLED = "trading_disabled"
    INVALID_TIMEOUT = "invalid_timeout"
    INVALID_PROVIDER = "invalid_provider"
    INVALID_MODE = "invalid_mode"
    LIVE_DISABLED = "live_disabled"


@dataclass(frozen=True)
class TradingValidationResult:
    """Structured outcome from Trading connector validation."""

    ok: bool
    code: TradingValidationCode
    message: str
    timeout_seconds: float = 30.0
    provider: str = "mock"
    mode: str = "paper"

    def format_report(self) -> str:
        """Return a multi-line French report for CLI output."""
        lines = ["=== Trading — validation du connecteur ===", ""]
        enabled = os.getenv("TITAN_TRADING_ENABLED", "true").lower() == "true"
        lines.append(f"Activé (TITAN_TRADING_ENABLED) : {'oui' if enabled else 'non'}")
        provider = os.getenv("TITAN_TRADING_PROVIDER", "mock")
        lines.append(f"TITAN_TRADING_PROVIDER : {provider}")
        mode = os.getenv("TITAN_TRADING_MODE", "paper")
        lines.append(f"TITAN_TRADING_MODE : {mode}")
        live_enabled = os.getenv("TITAN_TRADING_LIVE_ENABLED", "false").lower() == "true"
        lines.append(
            f"TITAN_TRADING_LIVE_ENABLED : {'oui' if live_enabled else 'non'}",
        )
        timeout = os.getenv("TITAN_TRADING_TIMEOUT_SECONDS", "30")
        lines.append(f"TITAN_TRADING_TIMEOUT_SECONDS : {timeout}")
        lines.append("")
        status = "PRÊT" if self.ok else "ÉCHEC"
        lines.append(f"Statut : {status} ({self.code.value})")
        lines.append(self.message)
        if self.ok and self.provider == "mock":
            lines.append("")
            lines.append(
                "Provider mock en mémoire — paper trading simulé, aucun broker connecté.",
            )
        return "\n".join(lines)


def validate_trading_config(
    *,
    enabled: bool | None = None,
    timeout_seconds: float | None = None,
    provider: str | None = None,
    mode: str | None = None,
    live_enabled: bool | None = None,
) -> TradingValidationResult:
    """Validate Trading connector configuration for production use."""
    is_enabled = (
        os.getenv("TITAN_TRADING_ENABLED", "true").lower() == "true"
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.TRADING_DISABLED,
            message=(
                "Connecteur Trading désactivé. Définissez TITAN_TRADING_ENABLED=true "
                "dans .env pour activer l'intégration."
            ),
        )

    raw_timeout = (
        os.getenv("TITAN_TRADING_TIMEOUT_SECONDS", "30")
        if timeout_seconds is None
        else str(timeout_seconds)
    )
    try:
        resolved_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.INVALID_TIMEOUT,
            message=f"TITAN_TRADING_TIMEOUT_SECONDS invalide : {raw_timeout!r}",
        )

    if resolved_timeout <= 0 or resolved_timeout > 120:
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.INVALID_TIMEOUT,
            message=(
                "TITAN_TRADING_TIMEOUT_SECONDS doit être entre 1 et 120 secondes."
            ),
            timeout_seconds=resolved_timeout,
        )

    resolved_provider = (
        TITAN_TRADING_PROVIDER if provider is None else provider.strip().lower()
    )
    if resolved_provider == "tradingview":
        if not TITAN_TRADINGVIEW_ENABLED:
            return TradingValidationResult(
                ok=False,
                code=TradingValidationCode.INVALID_PROVIDER,
                message=(
                    "Provider tradingview désactivé. "
                    "Définissez TITAN_TRADINGVIEW_ENABLED=true dans .env."
                ),
                timeout_seconds=resolved_timeout,
                provider=resolved_provider,
            )
        return TradingValidationResult(
            ok=True,
            code=TradingValidationCode.OK,
            message=(
                f"Connecteur TradingView prêt (alertes uniquement, "
                f"timeout={resolved_timeout}s). Aucun ordre exécuté."
            ),
            timeout_seconds=resolved_timeout,
            provider="tradingview",
            mode="paper",
        )

    if resolved_provider not in {"mock", "memory", "inmemory", "paper"}:
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.INVALID_PROVIDER,
            message=(
                f"TITAN_TRADING_PROVIDER invalide : {resolved_provider!r}. "
                "Valeurs supportées : mock, paper (Phase 16.1), "
                "tradingview (Phase 16.2). "
                "Apex, Rithmic et NinjaTrader non connectés."
            ),
            timeout_seconds=resolved_timeout,
            provider=resolved_provider,
        )

    resolved_mode = (
        TITAN_TRADING_MODE if mode is None else mode.strip().lower()
    )
    if resolved_mode not in {"paper", "simulation", "mock", "live"}:
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.INVALID_MODE,
            message=(
                f"TITAN_TRADING_MODE invalide : {resolved_mode!r}. "
                "Valeurs supportées : paper (défaut), simulation, mock, live."
            ),
            timeout_seconds=resolved_timeout,
            provider=resolved_provider,
            mode=resolved_mode,
        )

    is_live_enabled = (
        os.getenv("TITAN_TRADING_LIVE_ENABLED", "false").lower() == "true"
        if live_enabled is None
        else live_enabled
    )
    if resolved_mode == "live" and not is_live_enabled:
        return TradingValidationResult(
            ok=False,
            code=TradingValidationCode.LIVE_DISABLED,
            message=(
                "Mode live demandé mais TITAN_TRADING_LIVE_ENABLED=false. "
                "Le trading live nécessite une activation explicite dans .env."
            ),
            timeout_seconds=resolved_timeout,
            provider=resolved_provider,
            mode=resolved_mode,
        )

    mode_label = "paper" if resolved_mode in {"paper", "mock", "simulation"} else "live"
    return TradingValidationResult(
        ok=True,
        code=TradingValidationCode.OK,
        message=(
            f"Connecteur Trading prêt (provider={resolved_provider}, "
            f"mode={mode_label}, timeout={resolved_timeout}s). "
            "Lecture autorisée ; ordres avec confirmation."
        ),
        timeout_seconds=resolved_timeout,
        provider="mock" if resolved_provider in {"mock", "memory", "inmemory"} else resolved_provider,
        mode=mode_label,
    )

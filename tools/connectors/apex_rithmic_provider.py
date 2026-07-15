# =====================================
# Titan Apex/Rithmic Read-Only Provider
# =====================================

"""Apex/Rithmic read-only broker adapter scaffold (Phase 16.5).

Credential validation and readiness only — no Rithmic SDK imports, no live connections,
no order execution. All write operations remain blocked via ReadOnlyBrokerProvider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from config.settings import (
    TITAN_BROKER_READ_ONLY,
    TITAN_RITHMIC_ENABLED,
    TITAN_TRADING_LIVE_ENABLED,
)
from tools.connectors.broker_models import (
    BrokerAccount,
    BrokerOrder,
    BrokerPnL,
    BrokerPosition,
    BrokerReadinessReport,
)
from tools.connectors.read_only_broker_provider import (
    BrokerWriteBlockedError,
    ReadOnlyBrokerProvider,
)

APEX_RITHMIC_PROVIDER_KEY = "apex_rithmic"

_REQUIRED_CREDENTIAL_ENV = ("TITAN_RITHMIC_USERNAME", "TITAN_RITHMIC_PASSWORD")
_OPTIONAL_CREDENTIAL_ENV = (
    "TITAN_RITHMIC_SYSTEM",
    "TITAN_RITHMIC_SERVER",
    "TITAN_RITHMIC_APP_NAME",
    "TITAN_RITHMIC_APP_VERSION",
)


@dataclass(frozen=True)
class ApexRithmicCredentialStatus:
    """Non-secret credential presence snapshot for health reporting."""

    provider_enabled: bool
    credentials_present: bool
    missing_required: tuple[str, ...]
    read_only_active: bool
    execution_disabled: bool


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def apex_rithmic_credentials_present() -> bool:
    """Return True when all required Rithmic credential env vars are non-empty."""
    return all(_env_present(name) for name in _REQUIRED_CREDENTIAL_ENV)


def collect_apex_rithmic_credential_status(
    *,
    rithmic_enabled: bool | None = None,
    broker_read_only: bool | None = None,
    live_enabled: bool | None = None,
) -> ApexRithmicCredentialStatus:
    """Summarize Apex/Rithmic credential and safety flags without connecting."""
    enabled = TITAN_RITHMIC_ENABLED if rithmic_enabled is None else rithmic_enabled
    read_only = TITAN_BROKER_READ_ONLY if broker_read_only is None else broker_read_only
    live = TITAN_TRADING_LIVE_ENABLED if live_enabled is None else live_enabled
    missing = tuple(name for name in _REQUIRED_CREDENTIAL_ENV if not _env_present(name))
    return ApexRithmicCredentialStatus(
        provider_enabled=enabled,
        credentials_present=apex_rithmic_credentials_present(),
        missing_required=missing,
        read_only_active=read_only,
        execution_disabled=not live,
    )


def build_apex_rithmic_readiness_report(
    *,
    rithmic_enabled: bool | None = None,
    broker_read_only: bool | None = None,
    live_enabled: bool | None = None,
) -> BrokerReadinessReport:
    """Build readiness report for Apex/Rithmic without a live SDK connection."""
    status = collect_apex_rithmic_credential_status(
        rithmic_enabled=rithmic_enabled,
        broker_read_only=broker_read_only,
        live_enabled=live_enabled,
    )
    warnings: list[str] = [
        "Apex/Rithmic — adaptateur lecture seule Phase 16.5.",
        "Aucune connexion Rithmic réelle — scaffold credential-only.",
    ]

    if status.read_only_active:
        warnings.append("Mode lecture seule actif — TITAN_BROKER_READ_ONLY=true.")
    else:
        warnings.append(
            "Mode lecture seule inactif — TITAN_BROKER_READ_ONLY=false (provider bloqué)."
        )

    if status.execution_disabled:
        warnings.append("Exécution désactivée — TITAN_TRADING_LIVE_ENABLED=false.")
    else:
        warnings.append(
            "ATTENTION — TITAN_TRADING_LIVE_ENABLED=true mais exécution live "
            "non disponible en Phase 16.5."
        )

    if not status.provider_enabled:
        warnings.append("Provider désactivé — TITAN_RITHMIC_ENABLED=false.")
        return BrokerReadinessReport(
            provider_name=APEX_RITHMIC_PROVIDER_KEY,
            configured=False,
            credentials_present=status.credentials_present,
            read_only_supported=True,
            execution_supported=False,
            status="provider_disabled",
            warnings=tuple(warnings),
        )

    if not status.read_only_active:
        return BrokerReadinessReport(
            provider_name=APEX_RITHMIC_PROVIDER_KEY,
            configured=False,
            credentials_present=status.credentials_present,
            read_only_supported=True,
            execution_supported=False,
            status="blocked",
            warnings=tuple(warnings),
        )

    if not status.credentials_present:
        warnings.append(
            f"Identifiants manquants : {', '.join(status.missing_required)}."
        )
        return BrokerReadinessReport(
            provider_name=APEX_RITHMIC_PROVIDER_KEY,
            configured=False,
            credentials_present=False,
            read_only_supported=True,
            execution_supported=False,
            status="credentials_missing",
            warnings=tuple(warnings),
        )

    warnings.append(
        "Identifiants présents — intégration SDK Rithmic non connectée en Phase 16.5."
    )
    optional_present = [name for name in _OPTIONAL_CREDENTIAL_ENV if _env_present(name)]
    if optional_present:
        warnings.append(f"Config optionnelle détectée : {', '.join(optional_present)}.")

    return BrokerReadinessReport(
        provider_name=APEX_RITHMIC_PROVIDER_KEY,
        configured=True,
        credentials_present=True,
        read_only_supported=True,
        execution_supported=False,
        status="scaffold_ready",
        warnings=tuple(warnings),
    )


class ApexRithmicProvider(ReadOnlyBrokerProvider):
    """Read-only Apex/Rithmic scaffold — validates credentials, no SDK connection."""

    provider_name = APEX_RITHMIC_PROVIDER_KEY
    read_only_supported = True
    execution_supported = False

    def __init__(
        self,
        *,
        rithmic_enabled: bool | None = None,
        broker_read_only: bool | None = None,
        live_enabled: bool | None = None,
    ) -> None:
        self._rithmic_enabled = (
            TITAN_RITHMIC_ENABLED if rithmic_enabled is None else rithmic_enabled
        )
        self._broker_read_only = (
            TITAN_BROKER_READ_ONLY if broker_read_only is None else broker_read_only
        )
        self._live_enabled = (
            TITAN_TRADING_LIVE_ENABLED if live_enabled is None else live_enabled
        )
        self._readiness = build_apex_rithmic_readiness_report(
            rithmic_enabled=self._rithmic_enabled,
            broker_read_only=self._broker_read_only,
            live_enabled=self._live_enabled,
        )

    def readiness(self) -> BrokerReadinessReport:
        return self._readiness

    def _write_blocked_message(self, action: str) -> str:
        return (
            f"{action} bloqué — provider Apex/Rithmic en lecture seule (Phase 16.5). "
            "Exécution live désactivée — aucun ordre réel ne sera passé, "
            "même avec confirmed=true."
        )

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
        raise BrokerWriteBlockedError(self._write_blocked_message("place_order"))

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> BrokerOrder | None:
        raise BrokerWriteBlockedError(self._write_blocked_message("modify_order"))

    def cancel_order(self, order_id: str) -> bool:
        raise BrokerWriteBlockedError(self._write_blocked_message("cancel_order"))

    def flatten_position(
        self,
        account_id: str,
        *,
        symbol: str,
        market: str | None = None,
        source_signal_id: str = "",
    ) -> BrokerOrder | None:
        raise BrokerWriteBlockedError(self._write_blocked_message("flatten_position"))

    def _read_unavailable_error(self, operation: str) -> ValueError:
        report = self.readiness()
        if report.status == "provider_disabled":
            return ValueError(
                f"{operation} indisponible — provider Apex/Rithmic désactivé "
                "(TITAN_RITHMIC_ENABLED=false)."
            )
        if report.status == "blocked":
            return ValueError(
                f"{operation} indisponible — TITAN_BROKER_READ_ONLY=false. "
                "Phase 16.5 — lecture seule requise pour Apex/Rithmic."
            )
        if not report.credentials_present:
            missing = ", ".join(
                name
                for name in _REQUIRED_CREDENTIAL_ENV
                if not _env_present(name)
            )
            return ValueError(
                f"{operation} indisponible — identifiants Apex/Rithmic manquants "
                f"({missing}). Configurez les variables d'environnement requises."
            )
        return ValueError(
            f"{operation} indisponible — Apex/Rithmic scaffold Phase 16.5 "
            "(identifiants présents, aucune connexion SDK Rithmic)."
        )

    def list_accounts(self) -> list[BrokerAccount]:
        raise self._read_unavailable_error("list_accounts")

    def account_status(self, account_id: str) -> BrokerAccount | None:
        raise self._read_unavailable_error("account_status")

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[BrokerPosition]:
        raise self._read_unavailable_error("get_positions")

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[BrokerOrder]:
        raise self._read_unavailable_error("get_orders")

    def get_balance(self, account_id: str) -> tuple[float, float]:
        raise self._read_unavailable_error("get_balance")

    def get_market_status(self, market: str) -> str:
        raise self._read_unavailable_error("get_market_status")

    def get_pnl(self, account_id: str) -> BrokerPnL:
        raise self._read_unavailable_error("get_pnl")

    def get_margin(self, account_id: str) -> float:
        raise self._read_unavailable_error("get_margin")


def create_apex_rithmic_provider(
    *,
    rithmic_enabled: bool | None = None,
    broker_read_only: bool | None = None,
    live_enabled: bool | None = None,
) -> ApexRithmicProvider:
    """Instantiate the Apex/Rithmic read-only scaffold provider."""
    return ApexRithmicProvider(
        rithmic_enabled=rithmic_enabled,
        broker_read_only=broker_read_only,
        live_enabled=live_enabled,
    )

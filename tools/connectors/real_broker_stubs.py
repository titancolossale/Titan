# =====================================
# Titan Real Broker Read-Only Stubs
# =====================================

"""Read-only stub providers for future Apex/Rithmic/Tradovate/NinjaTrader (Phase 16.4).

No broker SDK imports. No live connections. Credentials are checked for readiness only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from tools.connectors.broker_models import (
    BrokerAccount,
    BrokerOrder,
    BrokerPnL,
    BrokerPosition,
    BrokerReadinessReport,
)
from tools.connectors.read_only_broker_provider import ReadOnlyBrokerProvider


@dataclass(frozen=True)
class _BrokerCredentialSpec:
    """Non-secret credential env var names checked for readiness."""

    provider_name: str
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...] = ()
    display_name: str = ""


_BROKER_CREDENTIAL_SPECS: dict[str, _BrokerCredentialSpec] = {
    "apex": _BrokerCredentialSpec(
        provider_name="apex",
        display_name="Apex",
        required_env=("TITAN_APEX_USERNAME", "TITAN_APEX_PASSWORD"),
        optional_env=("TITAN_APEX_ACCOUNT_ID", "TITAN_APEX_API_URL"),
    ),
    "rithmic": _BrokerCredentialSpec(
        provider_name="rithmic",
        display_name="Rithmic",
        required_env=("TITAN_RITHMIC_USERNAME", "TITAN_RITHMIC_PASSWORD"),
        optional_env=("TITAN_RITHMIC_SYSTEM", "TITAN_RITHMIC_GATEWAY"),
    ),
    "tradovate": _BrokerCredentialSpec(
        provider_name="tradovate",
        display_name="Tradovate",
        required_env=("TITAN_TRADOVATE_USERNAME", "TITAN_TRADOVATE_PASSWORD"),
        optional_env=("TITAN_TRADOVATE_API_KEY", "TITAN_TRADOVATE_ACCOUNT_ID"),
    ),
    "ninjatrader": _BrokerCredentialSpec(
        provider_name="ninjatrader",
        display_name="NinjaTrader",
        required_env=("TITAN_NINJATRADER_ACCOUNT",),
        optional_env=("TITAN_NINJATRADER_LICENSE", "TITAN_NINJATRADER_HOST"),
    ),
    "ninja": _BrokerCredentialSpec(
        provider_name="ninjatrader",
        display_name="NinjaTrader",
        required_env=("TITAN_NINJATRADER_ACCOUNT",),
        optional_env=("TITAN_NINJATRADER_LICENSE", "TITAN_NINJATRADER_HOST"),
    ),
}


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def credentials_present(spec: _BrokerCredentialSpec) -> bool:
    """Return True when all required credential env vars are non-empty."""
    return all(_env_present(name) for name in spec.required_env)


def build_readiness_report(provider_key: str) -> BrokerReadinessReport:
    """Build a readiness report for a future real broker provider."""
    normalized = provider_key.strip().lower()
    spec = _BROKER_CREDENTIAL_SPECS.get(normalized)
    if spec is None:
        return BrokerReadinessReport(
            provider_name=normalized,
            configured=False,
            credentials_present=False,
            read_only_supported=True,
            execution_supported=False,
            status="unknown",
            warnings=(f"Provider broker inconnu : {normalized!r}.",),
        )

    creds_ok = credentials_present(spec)
    configured = creds_ok
    warnings: list[str] = [
        f"{spec.display_name or spec.provider_name} — stub lecture seule Phase 16.4.",
        "Aucune connexion broker réelle — exécution désactivée.",
    ]
    if not creds_ok:
        missing = [name for name in spec.required_env if not _env_present(name)]
        warnings.append(
            f"Identifiants manquants : {', '.join(missing)}.",
        )
        status = "credentials_missing"
    else:
        warnings.append(
            "Identifiants détectés — intégration SDK non connectée en Phase 16.4.",
        )
        status = "stub_ready"

    return BrokerReadinessReport(
        provider_name=spec.provider_name,
        configured=configured,
        credentials_present=creds_ok,
        read_only_supported=True,
        execution_supported=False,
        status=status,
        warnings=tuple(warnings),
    )


class StubReadOnlyBrokerProvider(ReadOnlyBrokerProvider):
    """Shared read-only stub — no live API calls until a future phase."""

    def __init__(self, provider_key: str) -> None:
        normalized = provider_key.strip().lower()
        if normalized == "ninja":
            normalized = "ninjatrader"
        self._provider_key = normalized
        self.provider_name = normalized
        self._readiness = build_readiness_report(provider_key)

    def readiness(self) -> BrokerReadinessReport:
        return self._readiness

    def _not_connected_error(self, operation: str) -> ValueError:
        report = self.readiness()
        if not report.credentials_present:
            return ValueError(
                f"{operation} indisponible — identifiants {self.provider_name} manquants. "
                "Configurez les variables d'environnement requises."
            )
        return ValueError(
            f"{operation} indisponible — {self.provider_name} stub lecture seule "
            "(Phase 16.4, aucune connexion SDK)."
        )

    def list_accounts(self) -> list[BrokerAccount]:
        raise self._not_connected_error("list_accounts")

    def account_status(self, account_id: str) -> BrokerAccount | None:
        raise self._not_connected_error("account_status")

    def get_positions(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
    ) -> list[BrokerPosition]:
        raise self._not_connected_error("get_positions")

    def get_orders(
        self,
        account_id: str,
        *,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[BrokerOrder]:
        raise self._not_connected_error("get_orders")

    def get_balance(self, account_id: str) -> tuple[float, float]:
        raise self._not_connected_error("get_balance")

    def get_market_status(self, market: str) -> str:
        raise self._not_connected_error("get_market_status")

    def get_pnl(self, account_id: str) -> BrokerPnL:
        raise self._not_connected_error("get_pnl")

    def get_margin(self, account_id: str) -> float:
        raise self._not_connected_error("get_margin")


def create_real_broker_stub(provider_key: str) -> StubReadOnlyBrokerProvider:
    """Instantiate a read-only stub for a supported real broker name."""
    normalized = provider_key.strip().lower()
    aliases = {"ninja": "ninjatrader", "live": "apex"}
    resolved = aliases.get(normalized, normalized)
    if resolved not in {"apex", "rithmic", "tradovate", "ninjatrader"}:
        raise ValueError(f"Provider broker réel inconnu : {provider_key!r}")
    return StubReadOnlyBrokerProvider(resolved)


REAL_BROKER_PROVIDER_KEYS = frozenset({"apex", "rithmic", "tradovate", "ninjatrader", "ninja", "live"})

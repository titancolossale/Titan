# =====================================
# Titan Broker Readiness
# =====================================

"""Aggregate broker provider readiness reports (Phase 16.4 / 16.5)."""

from __future__ import annotations

from config.settings import (
    TITAN_BROKER_PROVIDER,
    TITAN_BROKER_READ_ONLY,
    TITAN_RITHMIC_ENABLED,
    TITAN_TRADING_LIVE_ENABLED,
    TITAN_TRADING_MODE,
    TITAN_TRADING_PROVIDER,
)
from tools.connectors.apex_rithmic_provider import (
    APEX_RITHMIC_PROVIDER_KEY,
    build_apex_rithmic_readiness_report,
    create_apex_rithmic_provider,
)
from tools.connectors.broker_models import BrokerReadinessReport
from tools.connectors.paper_broker_provider import PaperBrokerProvider
from tools.connectors.real_broker_stubs import (
    REAL_BROKER_PROVIDER_KEYS,
    build_readiness_report,
    create_real_broker_stub,
)
from tools.connectors.read_only_broker_provider import ReadOnlyBrokerProvider


_FUTURE_REAL_PROVIDERS = ("apex_rithmic", "apex", "rithmic", "tradovate", "ninjatrader")


def apex_rithmic_broker_readiness(
    *,
    rithmic_enabled: bool | None = None,
    broker_read_only: bool | None = None,
    live_enabled: bool | None = None,
) -> BrokerReadinessReport:
    """Readiness for the Apex/Rithmic read-only scaffold (Phase 16.5)."""
    return build_apex_rithmic_readiness_report(
        rithmic_enabled=rithmic_enabled,
        broker_read_only=broker_read_only,
        live_enabled=live_enabled,
    )


def paper_broker_readiness() -> BrokerReadinessReport:
    """Readiness for the in-memory paper broker."""
    return BrokerReadinessReport(
        provider_name="paper",
        configured=True,
        credentials_present=True,
        read_only_supported=False,
        execution_supported=True,
        status="ready",
        warnings=(
            "Paper broker — simulation uniquement, aucun capital réel.",
        ),
    )


def collect_broker_readiness_reports() -> list[BrokerReadinessReport]:
    """Return readiness for paper plus each future real broker provider."""
    reports = [paper_broker_readiness()]
    for provider_key in _FUTURE_REAL_PROVIDERS:
        if provider_key == APEX_RITHMIC_PROVIDER_KEY:
            reports.append(apex_rithmic_broker_readiness())
        else:
            reports.append(build_readiness_report(provider_key))
    return reports


def active_provider_readiness(
    *,
    provider: str | None = None,
    mode: str | None = None,
    live_enabled: bool | None = None,
    broker_read_only: bool | None = None,
) -> BrokerReadinessReport:
    """Readiness for the currently configured active provider."""
    resolved_provider = (
        provider or TITAN_BROKER_PROVIDER or TITAN_TRADING_PROVIDER
    ).strip().lower()
    resolved_read_only = (
        TITAN_BROKER_READ_ONLY if broker_read_only is None else broker_read_only
    )

    if resolved_provider in {"mock", "memory", "inmemory", "paper"}:
        report = paper_broker_readiness()
        if resolved_provider != "paper":
            return BrokerReadinessReport(
                provider_name=resolved_provider,
                configured=True,
                credentials_present=True,
                read_only_supported=False,
                execution_supported=True,
                status="ready",
                warnings=report.warnings + (
                    f"Alias {resolved_provider!r} -> PaperBrokerProvider.",
                ),
            )
        return report

    if resolved_provider == APEX_RITHMIC_PROVIDER_KEY:
        if not resolved_read_only:
            return BrokerReadinessReport(
                provider_name=APEX_RITHMIC_PROVIDER_KEY,
                configured=False,
                credentials_present=False,
                read_only_supported=True,
                execution_supported=False,
                status="blocked",
                warnings=(
                    "TITAN_BROKER_READ_ONLY=false — Apex/Rithmic bloqué en Phase 16.5.",
                    "Définissez TITAN_BROKER_READ_ONLY=true pour activer la lecture seule.",
                ),
            )
        return create_apex_rithmic_provider(broker_read_only=resolved_read_only).readiness()

    if resolved_provider in REAL_BROKER_PROVIDER_KEYS:
        if not resolved_read_only:
            return BrokerReadinessReport(
                provider_name=resolved_provider,
                configured=False,
                credentials_present=False,
                read_only_supported=True,
                execution_supported=False,
                status="blocked",
                warnings=(
                    "TITAN_BROKER_READ_ONLY=false — providers réels bloqués en Phase 16.4.",
                    "Définissez TITAN_BROKER_READ_ONLY=true pour activer la lecture seule.",
                ),
            )
        stub = create_real_broker_stub(resolved_provider)
        return stub.readiness()

    return BrokerReadinessReport(
        provider_name=resolved_provider,
        configured=False,
        credentials_present=False,
        read_only_supported=False,
        execution_supported=False,
        status="unknown",
        warnings=(f"Provider broker inconnu : {resolved_provider!r}.",),
    )


def trading_safety_snapshot(
    *,
    mode: str | None = None,
    live_enabled: bool | None = None,
    broker_read_only: bool | None = None,
) -> dict[str, object]:
    """Return global trading safety flags for health reporting."""
    resolved_mode = (mode or TITAN_TRADING_MODE).strip().lower()
    resolved_live = TITAN_TRADING_LIVE_ENABLED if live_enabled is None else live_enabled
    resolved_read_only = (
        TITAN_BROKER_READ_ONLY if broker_read_only is None else broker_read_only
    )
    return {
        "trading_mode": resolved_mode,
        "live_trading_enabled": resolved_live,
        "broker_read_only": resolved_read_only,
        "broker_provider": TITAN_BROKER_PROVIDER or TITAN_TRADING_PROVIDER,
        "rithmic_enabled": TITAN_RITHMIC_ENABLED,
        "paper_mode_active": resolved_mode == "paper",
        "live_execution_allowed": False,
    }


def format_broker_health_report(
    *,
    provider: str | None = None,
    mode: str | None = None,
    live_enabled: bool | None = None,
    broker_read_only: bool | None = None,
) -> str:
    """Format a French health report for CLI output."""
    safety = trading_safety_snapshot(
        mode=mode,
        live_enabled=live_enabled,
        broker_read_only=broker_read_only,
    )
    active = active_provider_readiness(
        provider=provider,
        mode=mode,
        live_enabled=live_enabled,
        broker_read_only=broker_read_only,
    )
    active_provider = (
        provider or TITAN_BROKER_PROVIDER or TITAN_TRADING_PROVIDER
    ).strip().lower()
    lines = [
        "=== Titan Broker Health (Phase 16.5) ===",
        "",
        "Configuration de sécurité :",
        f"  TITAN_TRADING_MODE              = {safety['trading_mode']}",
        f"  TITAN_TRADING_LIVE_ENABLED      = {str(safety['live_trading_enabled']).lower()}",
        f"  TITAN_BROKER_READ_ONLY          = {str(safety['broker_read_only']).lower()}",
        f"  TITAN_BROKER_PROVIDER           = {safety['broker_provider'] or '(via trading provider)'}",
        f"  TITAN_RITHMIC_ENABLED           = {str(safety['rithmic_enabled']).lower()}",
        f"  Exécution live autorisée        = non (Phase 16.5)",
        "",
        f"Provider actif ({active_provider}) :",
        f"  Statut                = {active.status}",
        f"  Configuré             = {'oui' if active.configured else 'non'}",
        f"  Identifiants présents = {'oui' if active.credentials_present else 'non'}",
        f"  Lecture seule         = {'oui' if active.read_only_supported else 'non'}",
        f"  Exécution supportée   = {'oui' if active.execution_supported else 'non'}",
    ]
    for warning in active.warnings:
        lines.append(f"  [!] {warning}")

    lines.extend(["", "Providers futurs (lecture seule) :"])
    for report in collect_broker_readiness_reports():
        if report.provider_name == "paper":
            continue
        creds = "présents" if report.credentials_present else "manquants"
        lines.append(
            f"  - {report.provider_name}: status={report.status}, "
            f"identifiants={creds}, exécution=non"
        )
        for warning in report.warnings[:2]:
            lines.append(f"      {warning}")

    lines.extend([
        "",
        "Opérations WRITE toujours bloquées sur providers réels :",
        "  place_order, modify_order, cancel_order, flatten_position",
    ])
    return "\n".join(lines)


def is_read_only_provider(provider: object) -> bool:
    """Return True when the provider must block all write operations."""
    if isinstance(provider, ReadOnlyBrokerProvider):
        return True
    if isinstance(provider, PaperBrokerProvider):
        return False
    return bool(getattr(provider, "read_only_supported", False))

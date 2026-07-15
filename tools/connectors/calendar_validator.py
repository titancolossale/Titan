# =====================================
# Titan Calendar Validator
# =====================================

"""Production readiness validation for the Calendar connector (Phase 14.1–14.2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from config.settings import (
    TITAN_CALENDAR_PROVIDER,
    TITAN_GOOGLE_CALENDAR_ENABLED,
    TITAN_GOOGLE_CLIENT_SECRET_PATH,
    TITAN_GOOGLE_TOKEN_PATH,
)
from tools.connectors.google_oauth import validate_client_secret_file


class CalendarValidationCode(str, Enum):
    """Machine-readable Calendar configuration status."""

    OK = "ok"
    CALENDAR_DISABLED = "calendar_disabled"
    INVALID_TIMEOUT = "invalid_timeout"
    INVALID_PROVIDER = "invalid_provider"
    GOOGLE_DISABLED = "google_disabled"
    GOOGLE_MISSING_CLIENT_SECRET = "google_missing_client_secret"
    GOOGLE_MISSING_TOKEN = "google_missing_token"


@dataclass(frozen=True)
class CalendarValidationResult:
    """Structured outcome from Calendar connector validation."""

    ok: bool
    code: CalendarValidationCode
    message: str
    timeout_seconds: float = 30.0
    provider: str = "mock"
    client_secret_path: Path | None = None
    token_path: Path | None = None

    def format_report(self) -> str:
        """Return a multi-line French report for CLI output."""
        lines = ["=== Calendar — validation du connecteur ===", ""]
        enabled = os.getenv("TITAN_CALENDAR_ENABLED", "true").lower() == "true"
        lines.append(f"Activé (TITAN_CALENDAR_ENABLED) : {'oui' if enabled else 'non'}")
        provider = os.getenv("TITAN_CALENDAR_PROVIDER", "mock")
        lines.append(f"TITAN_CALENDAR_PROVIDER : {provider}")
        google_enabled = os.getenv("TITAN_GOOGLE_CALENDAR_ENABLED", "false").lower() == "true"
        lines.append(
            f"TITAN_GOOGLE_CALENDAR_ENABLED : {'oui' if google_enabled else 'non'}",
        )
        timeout = os.getenv("TITAN_CALENDAR_TIMEOUT_SECONDS", "30")
        lines.append(f"TITAN_CALENDAR_TIMEOUT_SECONDS : {timeout}")
        if self.client_secret_path is not None:
            lines.append(f"TITAN_GOOGLE_CLIENT_SECRET_PATH : {self.client_secret_path}")
        if self.token_path is not None:
            lines.append(f"TITAN_GOOGLE_TOKEN_PATH : {self.token_path}")
        lines.append("")
        status = "PRÊT" if self.ok else "ÉCHEC"
        lines.append(f"Statut : {status} ({self.code.value})")
        lines.append(self.message)
        if self.ok and self.provider == "mock":
            lines.append("")
            lines.append(
                "Backend mock en mémoire — aucune connexion Google, Outlook ou Apple."
            )
        if self.ok and self.provider == "google":
            lines.append("")
            lines.append("Backend Google Calendar connecté (OAuth local).")
        if not self.ok and self.code == CalendarValidationCode.GOOGLE_MISSING_TOKEN:
            lines.append("")
            lines.append("Lance : python main.py calendar-auth")
        return "\n".join(lines)


def validate_calendar_config(
    *,
    enabled: bool | None = None,
    timeout_seconds: float | None = None,
    provider: str | None = None,
    google_enabled: bool | None = None,
    client_secret_path: Path | None = None,
    token_path: Path | None = None,
) -> CalendarValidationResult:
    """Validate Calendar connector configuration for production use."""
    is_enabled = (
        os.getenv("TITAN_CALENDAR_ENABLED", "true").lower() == "true"
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.CALENDAR_DISABLED,
            message=(
                "Connecteur Calendar désactivé. Définissez TITAN_CALENDAR_ENABLED=true "
                "dans .env pour activer l'intégration."
            ),
        )

    raw_timeout = (
        os.getenv("TITAN_CALENDAR_TIMEOUT_SECONDS", "30")
        if timeout_seconds is None
        else str(timeout_seconds)
    )
    try:
        resolved_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.INVALID_TIMEOUT,
            message=f"TITAN_CALENDAR_TIMEOUT_SECONDS invalide : {raw_timeout!r}",
        )

    if resolved_timeout <= 0 or resolved_timeout > 120:
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.INVALID_TIMEOUT,
            message=(
                "TITAN_CALENDAR_TIMEOUT_SECONDS doit être entre 1 et 120 secondes."
            ),
            timeout_seconds=resolved_timeout,
        )

    resolved_provider = (
        TITAN_CALENDAR_PROVIDER if provider is None else provider.strip().lower()
    )
    if resolved_provider not in {"mock", "memory", "inmemory", "google"}:
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.INVALID_PROVIDER,
            message=(
                f"TITAN_CALENDAR_PROVIDER invalide : {resolved_provider!r}. "
                "Valeurs supportées : mock, google."
            ),
            timeout_seconds=resolved_timeout,
            provider=resolved_provider,
        )

    if resolved_provider == "google":
        return _validate_google_config(
            resolved_timeout=resolved_timeout,
            google_enabled=google_enabled,
            client_secret_path=client_secret_path,
            token_path=token_path,
        )

    return CalendarValidationResult(
        ok=True,
        code=CalendarValidationCode.OK,
        message=(
            f"Connecteur Calendar prêt (backend mock, timeout={resolved_timeout}s). "
            "Lecture et recherche autorisées ; création/modification avec confirmation."
        ),
        timeout_seconds=resolved_timeout,
        provider="mock",
    )


def _validate_google_config(
    *,
    resolved_timeout: float,
    google_enabled: bool | None,
    client_secret_path: Path | None,
    token_path: Path | None,
) -> CalendarValidationResult:
    is_google_enabled = (
        TITAN_GOOGLE_CALENDAR_ENABLED if google_enabled is None else google_enabled
    )
    secret_path = client_secret_path or TITAN_GOOGLE_CLIENT_SECRET_PATH
    token_file = token_path or TITAN_GOOGLE_TOKEN_PATH

    if not is_google_enabled:
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.GOOGLE_DISABLED,
            message=(
                "Provider Google sélectionné mais TITAN_GOOGLE_CALENDAR_ENABLED=false. "
                "Définissez TITAN_GOOGLE_CALENDAR_ENABLED=true dans .env."
            ),
            timeout_seconds=resolved_timeout,
            provider="google",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    secret_ok, secret_message = validate_client_secret_file(secret_path)
    if not secret_ok:
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.GOOGLE_MISSING_CLIENT_SECRET,
            message=secret_message,
            timeout_seconds=resolved_timeout,
            provider="google",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    if not token_file.exists():
        return CalendarValidationResult(
            ok=False,
            code=CalendarValidationCode.GOOGLE_MISSING_TOKEN,
            message=(
                f"Token OAuth absent : {token_file}. "
                "Lancez python main.py calendar-auth pour vous authentifier."
            ),
            timeout_seconds=resolved_timeout,
            provider="google",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    return CalendarValidationResult(
        ok=True,
        code=CalendarValidationCode.OK,
        message=(
            f"Connecteur Google Calendar prêt (timeout={resolved_timeout}s). "
            f"{secret_message}"
        ),
        timeout_seconds=resolved_timeout,
        provider="google",
        client_secret_path=secret_path,
        token_path=token_file,
    )

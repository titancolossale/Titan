# =====================================
# Titan Email Validator
# =====================================

"""Production readiness validation for the Email connector (Phase 15.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from config.settings import (
    TITAN_EMAIL_PROVIDER,
    TITAN_GMAIL_CLIENT_SECRET_PATH,
    TITAN_GMAIL_ENABLED,
    TITAN_GMAIL_TOKEN_PATH,
)


class EmailValidationCode(str, Enum):
    """Machine-readable Email configuration status."""

    OK = "ok"
    EMAIL_DISABLED = "email_disabled"
    INVALID_TIMEOUT = "invalid_timeout"
    INVALID_PROVIDER = "invalid_provider"
    GMAIL_DISABLED = "gmail_disabled"
    GMAIL_MISSING_CLIENT_SECRET = "gmail_missing_client_secret"
    GMAIL_MISSING_TOKEN = "gmail_missing_token"


@dataclass(frozen=True)
class EmailValidationResult:
    """Structured outcome from Email connector validation."""

    ok: bool
    code: EmailValidationCode
    message: str
    timeout_seconds: float = 30.0
    provider: str = "mock"
    client_secret_path: Path | None = None
    token_path: Path | None = None

    def format_report(self) -> str:
        """Return a multi-line French report for CLI output."""
        lines = ["=== Email — validation du connecteur ===", ""]
        enabled = os.getenv("TITAN_EMAIL_ENABLED", "true").lower() == "true"
        lines.append(f"Activé (TITAN_EMAIL_ENABLED) : {'oui' if enabled else 'non'}")
        provider = os.getenv("TITAN_EMAIL_PROVIDER", "mock")
        lines.append(f"TITAN_EMAIL_PROVIDER : {provider}")
        gmail_enabled = os.getenv("TITAN_GMAIL_ENABLED", "false").lower() == "true"
        lines.append(
            f"TITAN_GMAIL_ENABLED : {'oui' if gmail_enabled else 'non'}",
        )
        timeout = os.getenv("TITAN_EMAIL_TIMEOUT_SECONDS", "30")
        lines.append(f"TITAN_EMAIL_TIMEOUT_SECONDS : {timeout}")
        if self.client_secret_path is not None:
            lines.append(f"TITAN_GMAIL_CLIENT_SECRET_PATH : {self.client_secret_path}")
        if self.token_path is not None:
            lines.append(f"TITAN_GMAIL_TOKEN_PATH : {self.token_path}")
        lines.append("")
        status = "PRÊT" if self.ok else "ÉCHEC"
        lines.append(f"Statut : {status} ({self.code.value})")
        lines.append(self.message)
        if self.ok and self.provider == "mock":
            lines.append("")
            lines.append(
                "Backend mock en mémoire — aucune connexion Gmail."
            )
        if self.ok and self.provider == "gmail":
            lines.append("")
            lines.append(
                "Backend Gmail connecté — OAuth token valide."
            )
        return "\n".join(lines)


def validate_email_config(
    *,
    enabled: bool | None = None,
    timeout_seconds: float | None = None,
    provider: str | None = None,
    gmail_enabled: bool | None = None,
    client_secret_path: Path | None = None,
    token_path: Path | None = None,
) -> EmailValidationResult:
    """Validate Email connector configuration for production use."""
    is_enabled = (
        os.getenv("TITAN_EMAIL_ENABLED", "true").lower() == "true"
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.EMAIL_DISABLED,
            message=(
                "Connecteur Email désactivé. Définissez TITAN_EMAIL_ENABLED=true "
                "dans .env pour activer l'intégration."
            ),
        )

    raw_timeout = (
        os.getenv("TITAN_EMAIL_TIMEOUT_SECONDS", "30")
        if timeout_seconds is None
        else str(timeout_seconds)
    )
    try:
        resolved_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.INVALID_TIMEOUT,
            message=f"TITAN_EMAIL_TIMEOUT_SECONDS invalide : {raw_timeout!r}",
        )

    if resolved_timeout <= 0 or resolved_timeout > 120:
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.INVALID_TIMEOUT,
            message=(
                "TITAN_EMAIL_TIMEOUT_SECONDS doit être entre 1 et 120 secondes."
            ),
            timeout_seconds=resolved_timeout,
        )

    resolved_provider = (
        TITAN_EMAIL_PROVIDER if provider is None else provider.strip().lower()
    )
    if resolved_provider not in {"mock", "memory", "inmemory", "gmail"}:
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.INVALID_PROVIDER,
            message=(
                f"TITAN_EMAIL_PROVIDER invalide : {resolved_provider!r}. "
                "Valeurs supportées : mock, gmail (Phase 15.2+)."
            ),
            timeout_seconds=resolved_timeout,
            provider=resolved_provider,
        )

    if resolved_provider == "gmail":
        return _validate_gmail_config(
            resolved_timeout=resolved_timeout,
            gmail_enabled=gmail_enabled,
            client_secret_path=client_secret_path,
            token_path=token_path,
        )

    return EmailValidationResult(
        ok=True,
        code=EmailValidationCode.OK,
        message=(
            f"Connecteur Email prêt (backend mock, timeout={resolved_timeout}s). "
            "Lecture et recherche autorisées ; modification avec confirmation."
        ),
        timeout_seconds=resolved_timeout,
        provider="mock",
    )


def _validate_gmail_config(
    *,
    resolved_timeout: float,
    gmail_enabled: bool | None,
    client_secret_path: Path | None,
    token_path: Path | None,
) -> EmailValidationResult:
    from tools.connectors.gmail_oauth import validate_gmail_client_secret_file

    is_gmail_enabled = (
        TITAN_GMAIL_ENABLED if gmail_enabled is None else gmail_enabled
    )
    secret_path = client_secret_path or TITAN_GMAIL_CLIENT_SECRET_PATH
    token_file = token_path or TITAN_GMAIL_TOKEN_PATH

    if not is_gmail_enabled:
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.GMAIL_DISABLED,
            message=(
                "Provider Gmail sélectionné mais TITAN_GMAIL_ENABLED=false. "
                "Définissez TITAN_GMAIL_ENABLED=true dans .env."
            ),
            timeout_seconds=resolved_timeout,
            provider="gmail",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    secret_ok, secret_message = validate_gmail_client_secret_file(secret_path)
    if not secret_ok:
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.GMAIL_MISSING_CLIENT_SECRET,
            message=secret_message,
            timeout_seconds=resolved_timeout,
            provider="gmail",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    if not token_file.exists():
        return EmailValidationResult(
            ok=False,
            code=EmailValidationCode.GMAIL_MISSING_TOKEN,
            message=(
                f"Token OAuth Gmail absent : {token_file}. "
                "Lancez python main.py email-auth pour vous authentifier."
            ),
            timeout_seconds=resolved_timeout,
            provider="gmail",
            client_secret_path=secret_path,
            token_path=token_file,
        )

    return EmailValidationResult(
        ok=True,
        code=EmailValidationCode.OK,
        message=(
            f"Connecteur Email prêt (backend Gmail, timeout={resolved_timeout}s). "
            "Lecture et recherche autorisées ; modification avec confirmation."
        ),
        timeout_seconds=resolved_timeout,
        provider="gmail",
        client_secret_path=secret_path,
        token_path=token_file,
    )

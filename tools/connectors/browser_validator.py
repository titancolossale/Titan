# =====================================
# Titan Browser Validator
# =====================================

"""Production readiness validation for the Browser connector (Phase 13.2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class BrowserValidationCode(str, Enum):
    """Machine-readable Browser configuration status."""

    OK = "ok"
    BROWSER_DISABLED = "browser_disabled"
    INVALID_TIMEOUT = "invalid_timeout"
    PLAYWRIGHT_MISSING = "playwright_missing"


@dataclass(frozen=True)
class BrowserValidationResult:
    """Structured outcome from Browser connector validation."""

    ok: bool
    code: BrowserValidationCode
    message: str
    timeout_seconds: float = 30.0
    playwright_available: bool = False

    def format_report(self) -> str:
        """Return a multi-line French report for CLI output."""
        lines = ["=== Browser — validation du connecteur ===", ""]
        enabled = os.getenv("TITAN_BROWSER_ENABLED", "false").lower() == "true"
        lines.append(f"Activé (TITAN_BROWSER_ENABLED) : {'oui' if enabled else 'non'}")
        timeout = os.getenv("TITAN_BROWSER_TIMEOUT_SECONDS", "30")
        lines.append(f"TITAN_BROWSER_TIMEOUT_SECONDS : {timeout}")
        headless = os.getenv("TITAN_BROWSER_HEADLESS", "true").lower() == "true"
        lines.append(f"TITAN_BROWSER_HEADLESS : {'oui' if headless else 'non'}")
        lines.append(f"Playwright installé : {'oui' if self.playwright_available else 'non'}")
        lines.append("")
        status = "PRÊT" if self.ok else "ÉCHEC"
        lines.append(f"Statut : {status} ({self.code.value})")
        lines.append(self.message)
        if self.ok:
            lines.append("")
            lines.append(
                "Phase 13.2 — backend Playwright. Lecture et inspection uniquement. "
                "Clics, formulaires et téléchargements nécessitent une confirmation."
            )
        return "\n".join(lines)


def _playwright_importable() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def validate_browser_config(
    *,
    enabled: bool | None = None,
    timeout_seconds: float | None = None,
    require_playwright: bool = True,
) -> BrowserValidationResult:
    """Validate Browser connector configuration for production use."""
    playwright_available = _playwright_importable()

    is_enabled = (
        os.getenv("TITAN_BROWSER_ENABLED", "false").lower() == "true"
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return BrowserValidationResult(
            ok=False,
            code=BrowserValidationCode.BROWSER_DISABLED,
            message=(
                "Connecteur Browser désactivé. Définissez TITAN_BROWSER_ENABLED=true "
                "dans .env pour activer l'intégration."
            ),
            playwright_available=playwright_available,
        )

    raw_timeout = (
        os.getenv("TITAN_BROWSER_TIMEOUT_SECONDS", "30")
        if timeout_seconds is None
        else str(timeout_seconds)
    )
    try:
        resolved_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return BrowserValidationResult(
            ok=False,
            code=BrowserValidationCode.INVALID_TIMEOUT,
            message=f"TITAN_BROWSER_TIMEOUT_SECONDS invalide : {raw_timeout!r}",
            playwright_available=playwright_available,
        )

    if resolved_timeout <= 0 or resolved_timeout > 120:
        return BrowserValidationResult(
            ok=False,
            code=BrowserValidationCode.INVALID_TIMEOUT,
            message=(
                "TITAN_BROWSER_TIMEOUT_SECONDS doit être entre 1 et 120 secondes."
            ),
            timeout_seconds=resolved_timeout,
            playwright_available=playwright_available,
        )

    if require_playwright and not playwright_available:
        return BrowserValidationResult(
            ok=False,
            code=BrowserValidationCode.PLAYWRIGHT_MISSING,
            message=(
                "Playwright requis pour le backend navigateur. "
                "Installez avec : pip install playwright && playwright install chromium"
            ),
            timeout_seconds=resolved_timeout,
            playwright_available=False,
        )

    return BrowserValidationResult(
        ok=True,
        code=BrowserValidationCode.OK,
        message=(
            f"Connecteur Browser prêt (Playwright, timeout={resolved_timeout}s). "
            "Lecture et inspection de pages web autorisées."
        ),
        timeout_seconds=resolved_timeout,
        playwright_available=playwright_available,
    )

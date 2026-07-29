# =====================================
# Titan Voice Enrollment Consent
# =====================================

"""Multi-language enrollment consent flow (Phase 20.9).

Records explicit consent before any voice sample is accepted. Does not collect
real Nolan/Ibrahim voices — preparation for a future consented enrollment step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


CONSENT_VERSION = "v1"


@dataclass(frozen=True)
class EnrollmentConsentPrompt:
    """Localized consent copy shown before enrollment samples."""

    locale: str
    language: str
    version: str
    title: str
    body: str
    checkbox_label: str
    decline_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "language": self.language,
            "version": self.version,
            "title": self.title,
            "body": self.body,
            "checkbox_label": self.checkbox_label,
            "decline_label": self.decline_label,
        }


CONSENT_FR = EnrollmentConsentPrompt(
    locale="fr-FR",
    language="fr",
    version=CONSENT_VERSION,
    title="Consentement d'enregistrement vocal",
    body=(
        "En continuant, tu acceptes que Titan traite temporairement des "
        "échantillons audio pour construire une empreinte vocale dérivée. "
        "L'audio brut n'est pas conservé. Tu peux annuler à tout moment. "
        "Aucun enregistrement réel de Nolan ou Ibrahim n'est collecté tant "
        "qu'une étape d'enrollment explicite n'est pas lancée."
    ),
    checkbox_label="J'accepte le traitement temporaire de mes échantillons vocaux.",
    decline_label="Refuser",
)

CONSENT_EN = EnrollmentConsentPrompt(
    locale="en-US",
    language="en",
    version=CONSENT_VERSION,
    title="Voice enrollment consent",
    body=(
        "By continuing, you agree that Titan may transiently process audio "
        "samples to build a derived voiceprint. Raw audio is not retained. "
        "You may cancel at any time. Real Nolan/Ibrahim voice samples are "
        "not collected until an explicit enrollment step is started."
    ),
    checkbox_label="I consent to temporary processing of my voice samples.",
    decline_label="Decline",
)

CONSENT_ES = EnrollmentConsentPrompt(
    locale="es-ES",
    language="es",
    version=CONSENT_VERSION,
    title="Consentimiento de registro de voz",
    body=(
        "Al continuar, aceptas que Titan procese temporalmente muestras de "
        "audio para construir una huella de voz derivada. El audio en bruto "
        "no se conserva. Puedes cancelar en cualquier momento."
    ),
    checkbox_label="Acepto el procesamiento temporal de mis muestras de voz.",
    decline_label="Rechazar",
)

_CONSENT_BY_LOCALE: dict[str, EnrollmentConsentPrompt] = {
    "fr": CONSENT_FR,
    "fr-FR": CONSENT_FR,
    "en": CONSENT_EN,
    "en-US": CONSENT_EN,
    "en-GB": CONSENT_EN,
    "es": CONSENT_ES,
    "es-ES": CONSENT_ES,
}


@dataclass(frozen=True)
class EnrollmentConsentRecord:
    """Immutable consent audit record (no biometrics)."""

    given: bool
    version: str
    locale: str
    recorded_at: str | None = None
    method: str = "explicit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "given": self.given,
            "version": self.version,
            "locale": self.locale,
            "recorded_at": self.recorded_at,
            "method": self.method,
        }


def get_consent_prompt(locale: str | None = None) -> EnrollmentConsentPrompt:
    """Resolve consent copy by locale (French default)."""
    key = (locale or "fr-FR").strip()
    if key in _CONSENT_BY_LOCALE:
        return _CONSENT_BY_LOCALE[key]
    lowered = key.lower()
    if lowered.startswith("en"):
        return CONSENT_EN
    if lowered.startswith("es"):
        return CONSENT_ES
    return CONSENT_FR


def list_consent_prompts() -> list[dict[str, Any]]:
    return [CONSENT_FR.to_dict(), CONSENT_EN.to_dict(), CONSENT_ES.to_dict()]


def record_consent(
    *,
    accepted: bool,
    locale: str | None = None,
    version: str | None = None,
    method: str = "explicit",
) -> EnrollmentConsentRecord:
    """Build a consent record timestamped in UTC."""
    prompt = get_consent_prompt(locale)
    now = datetime.now(timezone.utc).isoformat() if accepted else None
    return EnrollmentConsentRecord(
        given=bool(accepted),
        version=(version or prompt.version).strip() or CONSENT_VERSION,
        locale=prompt.locale,
        recorded_at=now,
        method=method,
    )


def require_valid_consent(record: EnrollmentConsentRecord | None) -> None:
    """Raise ValueError-compatible message code for callers."""
    if record is None or not record.given:
        raise ValueError("consent_required")
    if not record.version:
        raise ValueError("consent_version_missing")

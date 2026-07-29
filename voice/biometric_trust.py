# =====================================
# Titan Voice Biometric Trust Mode
# =====================================

"""Explicit DEVELOPMENT vs PRODUCTION biometric trust separation (Phase 20.12).

Histogram / development embeddings may remain available for automated tests and
development simulations only. Production speaker verification must refuse to
mark a speaker as trusted when only histogram/dev embeddings are available.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any


class BiometricTrustMode(str, Enum):
    """Application-level biometric trust policy."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


def resolve_biometric_trust_mode(
    raw: str | None = None,
) -> BiometricTrustMode:
    """Resolve trust mode from argument or ``TITAN_VOICE_BIOMETRIC_TRUST_MODE``."""
    value = (raw if raw is not None else os.getenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "")).strip().lower()
    if value in {"production", "prod"}:
        return BiometricTrustMode.PRODUCTION
    if value in {"development", "dev", "test"}:
        return BiometricTrustMode.DEVELOPMENT
    # Derive from Titan app env when unset — production deploys default strict.
    app_env = os.getenv("TITAN_APP_ENV", os.getenv("APP_ENV", "development")).strip().lower()
    if app_env in {"production", "prod", "railway"}:
        return BiometricTrustMode.PRODUCTION
    return BiometricTrustMode.DEVELOPMENT


def production_verification_defaults(
    mode: BiometricTrustMode | None = None,
) -> dict[str, bool]:
    """Default verification flags for the active trust mode."""
    trust_mode = mode or resolve_biometric_trust_mode()
    if trust_mode == BiometricTrustMode.PRODUCTION:
        return {
            "require_production_trust": True,
            "allow_dev_fallback_identity": False,
        }
    return {
        "require_production_trust": False,
        "allow_dev_fallback_identity": True,
    }


def biometric_trust_diagnostics(
    mode: BiometricTrustMode | None = None,
) -> dict[str, Any]:
    """Safe diagnostics for trust mode (no secrets / embeddings)."""
    trust_mode = mode or resolve_biometric_trust_mode()
    defaults = production_verification_defaults(trust_mode)
    return {
        "trust_mode": trust_mode.value,
        "histogram_allowed_for_trusted_identity": (
            trust_mode == BiometricTrustMode.DEVELOPMENT
        ),
        "require_production_trust_default": defaults["require_production_trust"],
        "allow_dev_fallback_identity_default": defaults[
            "allow_dev_fallback_identity"
        ],
        "production_rejects_histogram_trust": True,
    }

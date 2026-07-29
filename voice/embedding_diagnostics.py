# =====================================
# Titan Production Embedding Diagnostics
# =====================================

"""Safe diagnostics for Phase 20.11 / 20.12 speaker embeddings / verification.

Never exposes raw embeddings, encryption keys, or decrypted biometric payloads.
"""

from __future__ import annotations

from typing import Any

from voice.anti_spoof import get_anti_spoof_provider, get_anti_spoof_registry
from voice.biometric_trust import biometric_trust_diagnostics
from voice.diagnostics import emit_voice_diagnostic, sanitize_diagnostic_payload
from voice.ecapa_provider import ProviderInitStatus, probe_ecapa_dependencies
from voice.embedding_migration import EmbeddingMigrationService
from voice.embedding_provider import get_embedding_provider, get_embedding_registry
from voice.identity_security import IdentitySecurityBoundary
from voice.resemblyzer_provider import probe_resemblyzer_dependencies
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speaker_verification import VerificationConfig, default_verification_config


def collect_embedding_security_diagnostics(
    *,
    store: SpeakerProfileStore | None = None,
    verification_config: VerificationConfig | None = None,
) -> dict[str, Any]:
    """Aggregate production embedding / verification / security diagnostics."""
    provider = get_embedding_provider()
    registry = get_embedding_registry()
    anti = get_anti_spoof_provider()
    anti_registry = get_anti_spoof_registry()
    profile_store = store or SpeakerProfileStore()
    profile_store.load()
    migration = EmbeddingMigrationService(profile_store).public_status()
    security = IdentitySecurityBoundary().assert_not_authorization()
    thresholds = (verification_config or default_verification_config()).to_dict()
    trust = biometric_trust_diagnostics()

    profiles = profile_store.list_safe_profiles()
    profile_status = {
        "count": len(profiles),
        "active": sum(1 for p in profiles if p.get("active")),
        "revoked": sum(
            1 for p in profiles if p.get("enrollment_status") == "REVOKED"
        ),
        "production_trusted": sum(1 for p in profiles if p.get("production_trusted")),
        "dev_fallback": sum(
            1
            for p in profiles
            if str(p.get("embedding_version") or "").startswith("histogram")
        ),
    }

    init_status = getattr(provider, "init_status", None)
    if isinstance(init_status, ProviderInitStatus):
        init_status_value = init_status.value
    elif init_status is not None:
        init_status_value = str(init_status)
    else:
        init_status_value = "n/a"

    model_version = getattr(provider, "model_version", None)
    storage_health = profile_store.storage_health()

    snapshot: dict[str, Any] = {
        "ok": True,
        "embedding_provider": {
            "provider_id": provider.provider_id,
            "embedding_version": provider.embedding_version,
            "dimension": provider.dimension,
            "available": provider.is_available,
            "trust_level": provider.capabilities.trust_level.value,
            "is_production_trusted": provider.is_production_trusted,
            "is_dev_fallback": provider.is_dev_fallback,
            "backend_family": provider.capabilities.backend_family.value,
            "model_version": model_version,
            "init_status": init_status_value,
        },
        "embedding_version": provider.embedding_version,
        "providers": registry.list_providers(),
        "production_ready_providers": registry.list_production_ready(),
        "biometric_backend": {
            "ecapa": probe_ecapa_dependencies(),
            "resemblyzer": probe_resemblyzer_dependencies(),
            "active_provider_ready": bool(
                provider.is_available and not provider.is_dev_fallback
            ),
            "lazy_load": True,
            "affects_process_ready": False,
        },
        "trust_mode": trust,
        "verification": {
            "thresholds": thresholds,
            "verification_threshold": thresholds.get("high_threshold"),
            "prefers_unknown_over_false_id": True,
        },
        "profile_status": profile_status,
        "profiles": profiles,
        "migration_status": migration,
        "liveness": {
            "availability": anti.availability.value,
            "provider_id": anti.provider_id,
            "providers": anti_registry.list_providers(),
            "claims_perfect_anti_spoofing": False,
            "weakens_verification_when_unavailable": False,
        },
        "identity_security": security,
        "storage": {
            **storage_health,
            "envelope_version": storage_health.get("envelope_version"),
            "key_id": storage_health.get("key_id"),
            "migration_state": storage_health.get("migration_state"),
            "algorithm": storage_health.get("algorithm"),
        },
        "corruption_events": profile_store.list_corruption_events(limit=20),
        "phase_20_10b1_activation": True,
        "real_voice_collection_deferred": True,
        "phase_20_10b_deferred": True,
        "phase_20_12": True,
    }

    cleaned = sanitize_diagnostic_payload(snapshot)
    emit_voice_diagnostic(
        "VOICE_EMBEDDING_SECURITY_SNAPSHOT",
        embedding_version=provider.embedding_version,
        trust_level=provider.capabilities.trust_level.value,
        production_trusted=provider.is_production_trusted,
        active_profiles=profile_status["active"],
        liveness=anti.availability.value,
        migration_plans=len(migration.get("migration", {}).get("plans", [])),
        trust_mode=trust.get("trust_mode"),
        init_status=init_status_value,
        envelope_version=storage_health.get("envelope_version"),
    )
    return cleaned


def collect_biometric_readiness() -> dict[str, Any]:
    """Separate biometric readiness — never fails process ``/ready``."""
    provider = get_embedding_provider()
    init_status = getattr(provider, "init_status", None)
    init_value = (
        init_status.value
        if isinstance(init_status, ProviderInitStatus)
        else (str(init_status) if init_status is not None else "n/a")
    )
    ecapa = probe_ecapa_dependencies()
    resemblyzer = probe_resemblyzer_dependencies()
    ready = bool(
        provider.is_available
        and provider.is_production_trusted
        and init_value in {"ready", "not_loaded", "n/a"}
    )
    return {
        "name": "voice_biometric",
        "status": "available" if ready else "unavailable",
        "required": False,
        "healthy": ready if provider.is_available else None,
        "message": (
            f"Biometric provider {provider.provider_id} "
            f"(init={init_value}, trust={provider.capabilities.trust_level.value})"
        ),
        "provider_id": provider.provider_id,
        "embedding_version": provider.embedding_version,
        "model_version": getattr(provider, "model_version", None),
        "init_status": init_value,
        "ecapa_deps": ecapa.get("available"),
        "resemblyzer_deps": resemblyzer.get("available"),
        "affects_ready": False,
    }

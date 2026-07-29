# =====================================
# Titan Production Enrollment Pre-flight
# =====================================

"""Phase 20.10B-1 — validate production enrollment readiness WITHOUT recording.

Runs a complete pre-flight for ECAPA, production biometric trust, AES-GCM,
enrollment storage, microphone capability, consent workflow, and Nolan/Ibrahim
profile slots. Never collects biometric samples. Never prints encryption keys
or raw embeddings.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from context.session_manager import AUTHORIZED_USERS
from voice.audio_devices import AudioDeviceManager
from voice.biometric_trust import (
    BiometricTrustMode,
    biometric_trust_diagnostics,
    resolve_biometric_trust_mode,
)
from voice.diagnostics import emit_voice_diagnostic, sanitize_diagnostic_payload
from voice.ecapa_provider import ProviderInitStatus, normalize_embedding, probe_ecapa_dependencies
from voice.embedding_capabilities import EmbeddingTrustLevel
from voice.embedding_provider import (
    get_embedding_provider,
    get_embedding_registry,
    reset_embedding_registry_for_tests,
)
from voice.embedding_storage import AesGcmEmbeddingStorage, build_embedding_storage
from voice.enrollment_consent import get_consent_prompt, list_consent_prompts
from voice.enrollment_scripts import list_enrollment_scripts
from voice.identity_security import (
    IdentityAssertionKind,
    IdentitySecurityBoundary,
    voice_identity_may_access_personal_memory,
)
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speaker_verification import SpeakerVerificationEngine, default_verification_config


class PreflightStatus(str, Enum):
    """Per-check readiness status."""

    READY = "READY"
    NOT_READY = "NOT_READY"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


@dataclass
class PreflightCheck:
    """One named readiness check."""

    name: str
    status: PreflightStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }


def _status_rank(status: PreflightStatus) -> int:
    return {
        PreflightStatus.READY: 0,
        PreflightStatus.WARNING: 1,
        PreflightStatus.SKIPPED: 2,
        PreflightStatus.NOT_READY: 3,
    }.get(status, 3)


def _slot_status(
    store: SpeakerProfileStore,
    user_id: str,
) -> PreflightCheck:
    """Nolan/Ibrahim profile slot readiness — empty slots are READY for enrollment."""
    store.load()
    active = store.get_active_profile(user_id)
    profiles = store.list_safe_profiles(user_id=user_id)
    in_flight = store.get_active_session_for_user(user_id)
    details = {
        "user_id": user_id,
        "slot_reserved": True,
        "active_profile": bool(active and active.active),
        "profile_count": len(profiles),
        "biometric_enrolled": bool(active and active.active),
        "in_flight_session": bool(in_flight),
        "production_trusted_profile": bool(
            active and getattr(active, "production_trusted", False)
        ),
    }
    if in_flight:
        return PreflightCheck(
            name=f"{user_id.lower()}_profile_slot",
            status=PreflightStatus.WARNING,
            message=(
                f"{user_id} slot has an in-flight enrollment session "
                f"({in_flight.session_id}); cancel or recover before a new run."
            ),
            details=details,
        )
    if active and active.active:
        return PreflightCheck(
            name=f"{user_id.lower()}_profile_slot",
            status=PreflightStatus.WARNING,
            message=(
                f"{user_id} already has an active voice profile. "
                "Replacement enrollment is allowed with explicit consent."
            ),
            details=details,
        )
    return PreflightCheck(
        name=f"{user_id.lower()}_profile_slot",
        status=PreflightStatus.READY,
        message=f"{user_id} enrollment slot is empty and ready.",
        details=details,
    )


def _check_ecapa(*, force_load: bool = True) -> PreflightCheck:
    deps = probe_ecapa_dependencies()
    provider = get_embedding_provider()
    registry = get_embedding_registry()
    details: dict[str, Any] = {
        "configured_provider": os.getenv("TITAN_VOICE_EMBEDDING_PROVIDER", ""),
        "active_provider_id": provider.provider_id,
        "embedding_version": provider.embedding_version,
        "available": provider.is_available,
        "trust_level": provider.capabilities.trust_level.value,
        "is_production_trusted": provider.is_production_trusted,
        "is_dev_fallback": provider.is_dev_fallback,
        "ecapa_deps": deps,
        "production_ready_providers": registry.list_production_ready(),
        "normalization_ok": False,
        "histogram_cannot_grant_production": True,
    }

    # Histogram must never grant production trust.
    try:
        hist = registry.get("histogram")
        details["histogram_trust_level"] = hist.capabilities.trust_level.value
        details["histogram_is_production_trusted"] = hist.is_production_trusted
        if hist.is_production_trusted:
            return PreflightCheck(
                name="ecapa_provider",
                status=PreflightStatus.NOT_READY,
                message="Histogram incorrectly reports production trust.",
                details=details,
            )
    except Exception as exc:
        details["histogram_probe_error"] = type(exc).__name__

    if provider.provider_id != "ecapa":
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message=(
                f"Active embedding provider is {provider.provider_id!r}; "
                "expected ecapa for production enrollment."
            ),
            details=details,
        )

    if not provider.is_available:
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message="ECAPA provider registered but dependencies unavailable.",
            details=details,
        )

    if provider.capabilities.trust_level != EmbeddingTrustLevel.PRODUCTION:
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message=f"ECAPA trust level is {provider.capabilities.trust_level.value}, not production.",
            details=details,
        )

    # Normalization smoke (unit vector).
    unit = normalize_embedding([3.0, 4.0, 0.0])
    details["normalization_ok"] = (
        abs(unit[0] - 0.6) < 1e-9 and abs(unit[1] - 0.8) < 1e-9
    )
    if not details["normalization_ok"]:
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message="Embedding normalization check failed.",
            details=details,
        )

    init_status = getattr(provider, "init_status", None)
    init_value = (
        init_status.value
        if isinstance(init_status, ProviderInitStatus)
        else (str(init_status) if init_status is not None else "n/a")
    )
    details["init_status"] = init_value

    if force_load and hasattr(provider, "ensure_loaded"):
        try:
            provider.ensure_loaded()  # type: ignore[attr-defined]
            init_status = getattr(provider, "init_status", None)
            init_value = (
                init_status.value
                if isinstance(init_status, ProviderInitStatus)
                else str(init_status)
            )
            details["init_status"] = init_value
        except Exception as exc:
            details["load_error"] = type(exc).__name__
            return PreflightCheck(
                name="ecapa_provider",
                status=PreflightStatus.NOT_READY,
                message=f"ECAPA model failed to load: {type(exc).__name__}",
                details=details,
            )

    if init_value not in {"ready", "not_loaded", "n/a"}:
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message=f"ECAPA init_status={init_value}",
            details=details,
        )

    # Verification engine must resolve to the same active provider.
    engine = SpeakerVerificationEngine(config=default_verification_config())
    engine_provider = engine._provider_or_default()  # noqa: SLF001 — preflight only
    details["verification_provider_id"] = engine_provider.provider_id
    if engine_provider.provider_id != "ecapa":
        return PreflightCheck(
            name="ecapa_provider",
            status=PreflightStatus.NOT_READY,
            message=(
                f"Verification engine uses {engine_provider.provider_id!r}, not ecapa."
            ),
            details=details,
        )

    return PreflightCheck(
        name="ecapa_provider",
        status=PreflightStatus.READY,
        message="ECAPA provider loaded, production-trusted, verification-bound.",
        details=details,
    )


def _check_production_trust() -> PreflightCheck:
    mode = resolve_biometric_trust_mode()
    trust = biometric_trust_diagnostics(mode)
    details = dict(trust)
    details["env_trust_mode"] = os.getenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "")
    details["require_production_trust_env"] = os.getenv(
        "TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST", ""
    )
    details["allow_dev_identity_env"] = os.getenv(
        "TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY", ""
    )

    boundary = IdentitySecurityBoundary()
    claimed = boundary.evaluate_assertion(IdentityAssertionKind.CLAIMED_IDENTITY)
    details["claimed_vs_verified"] = {
        "claimed_is_biometrically_verified": claimed.is_biometrically_verified,
        "claimed_may_access_personal_memory": claimed.may_access_personal_memory,
        "claimed_assertion": claimed.assertion_kind.value,
        "voice_identity_may_access_personal_memory_for_claimed": (
            voice_identity_may_access_personal_memory(
                assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY
            )
        ),
    }

    if mode != BiometricTrustMode.PRODUCTION:
        return PreflightCheck(
            name="production_trust",
            status=PreflightStatus.NOT_READY,
            message=f"Biometric trust mode is {mode.value}, expected production.",
            details=details,
        )

    if trust.get("histogram_allowed_for_trusted_identity"):
        return PreflightCheck(
            name="production_trust",
            status=PreflightStatus.NOT_READY,
            message="Histogram must not be allowed for trusted identity in production.",
            details=details,
        )

    if claimed.is_biometrically_verified or claimed.may_access_personal_memory:
        return PreflightCheck(
            name="production_trust",
            status=PreflightStatus.NOT_READY,
            message="CLAIMED_IDENTITY incorrectly elevates to verified/personal memory.",
            details=details,
        )

    return PreflightCheck(
        name="production_trust",
        status=PreflightStatus.READY,
        message="Production trust active; CLAIMED_IDENTITY != VERIFIED_IDENTITY.",
        details=details,
    )


def _check_aes_gcm() -> PreflightCheck:
    encryption_flag = (
        os.getenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "false").lower() == "true"
    )
    key_present = bool(os.getenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", "").strip())
    key_id = os.getenv("TITAN_VOICE_EMBEDDING_KEY_ID", "primary").strip() or "primary"
    details: dict[str, Any] = {
        "encryption_enabled": encryption_flag,
        "storage_key_configured": key_present,
        "key_id": key_id,
        "key_value_exposed": False,
        "roundtrip_ok": False,
        "using_dev_key": None,
        "algorithm": "AES-256-GCM",
    }

    if not encryption_flag:
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message="TITAN_VOICE_EMBEDDING_ENCRYPTION is not true.",
            details=details,
        )

    if not key_present:
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message=(
                "TITAN_VOICE_EMBEDDING_STORAGE_KEY is missing. "
                "Run: python scripts/ensure_voice_embedding_storage_key.py"
            ),
            details=details,
        )

    storage = build_embedding_storage(prefer_encryption=True)
    health = storage.health_dict()
    details["using_dev_key"] = health.get("using_dev_key")
    details["codec"] = health.get("codec")
    details["envelope_version"] = health.get("envelope_version")

    if not isinstance(storage, AesGcmEmbeddingStorage):
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message=f"Storage backend is {type(storage).__name__}, expected AesGcm.",
            details=details,
        )

    if health.get("using_dev_key"):
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message="AES-GCM is using the development key — configure a real storage key.",
            details=details,
        )

    # Round-trip with synthetic vectors (never real biometrics).
    from voice.embedding_storage import wrap_profile_embeddings, unwrap_profile_embeddings

    payload = wrap_profile_embeddings(
        profile_id="preflight-probe",
        user_id="preflight",
        embedding_version="ecapa_v1",
        embeddings=[[0.1, 0.2, 0.3]],
        backend=storage,
    )
    if payload.get("vectors"):
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message="Encrypted envelope still contains plaintext vectors.",
            details=details,
        )
    bundle_vectors = unwrap_profile_embeddings(payload, backend=storage)
    details["roundtrip_ok"] = bundle_vectors == [[0.1, 0.2, 0.3]]
    if not details["roundtrip_ok"]:
        return PreflightCheck(
            name="aes_gcm",
            status=PreflightStatus.NOT_READY,
            message="AES-GCM encrypt/decrypt round-trip failed.",
            details=details,
        )

    return PreflightCheck(
        name="aes_gcm",
        status=PreflightStatus.READY,
        message="AES-256-GCM storage key configured; encrypt/decrypt ready.",
        details=details,
    )


def _check_enrollment_storage(store: SpeakerProfileStore) -> PreflightCheck:
    store.load()
    health = store.storage_health()
    file_path = store.file_path
    if file_path is None:
        try:
            from config import settings as app_settings

            file_path = Path(app_settings.TITAN_VOICE_SPEAKER_PROFILES_PATH)
            store.file_path = file_path
        except Exception:
            file_path = Path("data/voice_speaker_profiles.json")
            store.file_path = file_path
    details = {
        "path": str(file_path),
        "path_writable": False,
        "schema_version": health.get("schema_version"),
        "encryption_enabled": health.get("encryption_enabled"),
        "codec": health.get("codec"),
        "key_id": health.get("key_id"),
        "using_dev_key": health.get("using_dev_key"),
        "retain_raw_audio": health.get("retain_raw_audio"),
    }
    try:
        parent = file_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        details["path_writable"] = parent.exists() and os.access(parent, os.W_OK)
    except OSError as exc:
        details["path_error"] = type(exc).__name__

    if health.get("retain_raw_audio"):
        return PreflightCheck(
            name="enrollment_storage",
            status=PreflightStatus.WARNING,
            message="Raw audio retention is enabled — disable for production enrollment.",
            details=details,
        )

    if not details["path_writable"]:
        return PreflightCheck(
            name="enrollment_storage",
            status=PreflightStatus.NOT_READY,
            message=f"Enrollment profile path not writable: {file_path}",
            details=details,
        )

    if not health.get("encryption_enabled"):
        return PreflightCheck(
            name="enrollment_storage",
            status=PreflightStatus.NOT_READY,
            message="Profile store encryption is not enabled.",
            details=details,
        )

    if health.get("using_dev_key"):
        return PreflightCheck(
            name="enrollment_storage",
            status=PreflightStatus.NOT_READY,
            message="Profile store is still on the development encryption key.",
            details=details,
        )

    return PreflightCheck(
        name="enrollment_storage",
        status=PreflightStatus.READY,
        message="Encrypted enrollment profile storage is ready.",
        details=details,
    )


def _check_microphone() -> PreflightCheck:
    """Server-side mic capability — browser MediaDevices is the live capture path."""
    devices = AudioDeviceManager()
    inputs = devices.list_input_devices()
    details = {
        "server_input_device_count": len(inputs),
        "server_default_input": next(
            (d.to_dict() for d in inputs if d.is_default), None
        ),
        "browser_capture_path": "web/v2/voice/microphone.js + enrollment-ui.js",
        "always_listening": os.getenv("TITAN_VOICE_ALWAYS_LISTENING", "false"),
        "wake_word_enabled": os.getenv("TITAN_VOICE_WAKE_WORD_ENABLED", "false"),
        "note": (
            "Live capture uses the Web App MediaDevices path; "
            "server device list is advisory."
        ),
    }
    if os.getenv("TITAN_VOICE_ALWAYS_LISTENING", "false").lower() == "true":
        return PreflightCheck(
            name="microphone",
            status=PreflightStatus.NOT_READY,
            message="Always-listening must remain disabled for enrollment activation.",
            details=details,
        )
    if os.getenv("TITAN_VOICE_WAKE_WORD_ENABLED", "false").lower() == "true":
        return PreflightCheck(
            name="microphone",
            status=PreflightStatus.NOT_READY,
            message="Wake-word must remain disabled for enrollment activation.",
            details=details,
        )
    if not inputs:
        return PreflightCheck(
            name="microphone",
            status=PreflightStatus.WARNING,
            message=(
                "No server-side input devices listed; Web App mic path still usable."
            ),
            details=details,
        )
    return PreflightCheck(
        name="microphone",
        status=PreflightStatus.READY,
        message="Microphone capability ready (Web App push-to-talk enrollment path).",
        details=details,
    )


def _check_consent() -> PreflightCheck:
    require = os.getenv("TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT", "true").lower() == "true"
    prompts = list_consent_prompts()
    scripts = list_enrollment_scripts()
    fr = get_consent_prompt("fr-FR")
    en = get_consent_prompt("en-US")
    details = {
        "require_consent": require,
        "consent_prompt_count": len(prompts),
        "script_count": len(scripts),
        "fr_title": fr.title if fr else None,
        "en_title": en.title if en else None,
        "authorized_users": sorted(AUTHORIZED_USERS),
    }
    if not require:
        return PreflightCheck(
            name="consent_workflow",
            status=PreflightStatus.NOT_READY,
            message="Consent requirement is disabled — enable for production enrollment.",
            details=details,
        )
    if not prompts or not scripts:
        return PreflightCheck(
            name="consent_workflow",
            status=PreflightStatus.NOT_READY,
            message="Consent prompts or enrollment scripts missing.",
            details=details,
        )
    return PreflightCheck(
        name="consent_workflow",
        status=PreflightStatus.READY,
        message="Consent workflow and enrollment scripts are ready.",
        details=details,
    )


def run_enrollment_preflight(
    *,
    store: SpeakerProfileStore | None = None,
    force_ecapa_load: bool = True,
    reset_registry: bool = False,
) -> dict[str, Any]:
    """Run full production enrollment pre-flight (no biometric recording)."""
    started = time.perf_counter()
    if reset_registry:
        reset_embedding_registry_for_tests()

    profile_store = store
    if profile_store is None:
        try:
            from config import settings as app_settings

            profile_store = SpeakerProfileStore(
                file_path=app_settings.TITAN_VOICE_SPEAKER_PROFILES_PATH
            )
        except Exception:
            profile_store = SpeakerProfileStore(
                file_path=Path("data/voice_speaker_profiles.json")
            )
    checks = [
        _check_ecapa(force_load=force_ecapa_load),
        _check_production_trust(),
        _check_aes_gcm(),
        _check_enrollment_storage(profile_store),
        _check_microphone(),
        _check_consent(),
        _slot_status(profile_store, "Nolan"),
        _slot_status(profile_store, "Ibrahim"),
    ]

    worst = max(checks, key=lambda c: _status_rank(c.status)).status
    ready = all(
        c.status in {PreflightStatus.READY, PreflightStatus.WARNING} for c in checks
    ) and not any(c.status == PreflightStatus.NOT_READY for c in checks)

    blocking = [c.name for c in checks if c.status == PreflightStatus.NOT_READY]
    warnings = [c.name for c in checks if c.status == PreflightStatus.WARNING]

    snapshot: dict[str, Any] = {
        "ok": ready,
        "ready_for_real_enrollment": ready,
        "overall_status": (
            PreflightStatus.READY.value
            if ready and not warnings
            else (
                PreflightStatus.WARNING.value
                if ready
                else PreflightStatus.NOT_READY.value
            )
        ),
        "phase": "20.10B-1",
        "records_biometric_samples": False,
        "blocking_checks": blocking,
        "warning_checks": warnings,
        "checks": {c.name: c.to_dict() for c in checks},
        "check_list": [c.to_dict() for c in checks],
        "enrollment_method": {
            "primary": "web_app_voice_panel",
            "path": "web/v2/voice/enrollment-ui.js",
            "guided_cli": "scripts/phase20_10b1_guided_enroll.py",
            "preflight_cli": "scripts/phase20_10b1_enrollment_preflight.py",
        },
        "safety": {
            "nolan_ibrahim_isolated": True,
            "claimed_identity_not_verified": True,
            "voice_not_sole_authorization": True,
            "wake_word_disabled_required": True,
            "always_listening_disabled_required": True,
            "no_real_recording_in_preflight": True,
        },
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "worst_status": worst.value,
    }
    cleaned = sanitize_diagnostic_payload(snapshot)
    emit_voice_diagnostic(
        "VOICE_ENROLLMENT_PREFLIGHT",
        ready=ready,
        overall=cleaned.get("overall_status"),
        blocking=len(blocking),
        warnings=len(warnings),
    )
    return cleaned

# =====================================
# Titan Phase 20.10B-1 — Production Enrollment Activation
# =====================================

"""ECAPA production activation, trust, AES-GCM, preflight, enrollment safety.

Never records real Nolan/Ibrahim voices.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import pytest

from voice.audio_prep import floats_to_pcm16_wav
from voice.biometric_trust import BiometricTrustMode, resolve_biometric_trust_mode
from voice.ecapa_provider import EcapaEmbeddingProvider, normalize_embedding
from voice.embedding_capabilities import EmbeddingTrustLevel
from voice.embedding_provider import (
    HistogramEmbeddingProvider,
    get_embedding_provider,
    reset_embedding_registry_for_tests,
    set_embedding_provider,
)
from voice.embedding_storage import (
    AesGcmEmbeddingStorage,
    build_embedding_storage,
    unwrap_profile_embeddings,
    wrap_profile_embeddings,
)
from voice.enrollment_preflight import PreflightStatus, run_enrollment_preflight
from voice.exceptions import VoiceEnrollmentError
from voice.identity_security import (
    IdentityAssertionKind,
    IdentitySecurityBoundary,
    voice_identity_may_access_personal_memory,
)
from voice.speaker_identifier import SpeakerIdentifier, SpeakerIdentity
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    VerificationConfig,
    VerificationDecision,
)
from voice.voice_enrollment import VoiceEnrollmentService
from voice.enrollment_models import EnrollmentConfig


def _synthetic_tone(seed: int, n: int = 16000, rate: int = 16000) -> bytes:
    samples = [
        0.25 * math.sin(2 * math.pi * (180 + seed * 17) * (i / rate))
        + 0.1 * math.sin(2 * math.pi * (90 + seed) * (i / rate))
        for i in range(n)
    ]
    return floats_to_pcm16_wav(samples, sample_rate=rate)


def _fake_ecapa_inference(audio: bytes) -> list[float]:
    digest = hashlib.sha256(audio).digest()
    values: list[float] = []
    seed = digest
    while len(values) < 192:
        seed = hashlib.sha256(seed).digest()
        for byte in seed:
            if len(values) >= 192:
                break
            values.append((byte / 127.5) - 1.0)
    return normalize_embedding(values)


@pytest.fixture(autouse=True)
def _reset_registries(monkeypatch):
    monkeypatch.delenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY", raising=False)
    reset_embedding_registry_for_tests()
    set_embedding_provider(None)
    yield
    reset_embedding_registry_for_tests()
    set_embedding_provider(None)


def _activate_production_env(monkeypatch, tmp_path: Path) -> SpeakerProfileStore:
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_PROVIDER", "ecapa")
    monkeypatch.setenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "production")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST", "true")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY", "false")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "true")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", "test-phase20-10b1-key-material")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_KEY_ID", "primary")
    monkeypatch.setenv("TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT", "true")
    monkeypatch.setenv("TITAN_VOICE_ALWAYS_LISTENING", "false")
    monkeypatch.setenv("TITAN_VOICE_WAKE_WORD_ENABLED", "false")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO", "false")
    reset_embedding_registry_for_tests()
    provider = EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference)
    set_embedding_provider(provider)
    return SpeakerProfileStore(file_path=tmp_path / "profiles.json")


def test_ecapa_production_activation(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    provider = get_embedding_provider()
    assert provider.provider_id == "ecapa"
    assert provider.is_available
    assert provider.capabilities.trust_level == EmbeddingTrustLevel.PRODUCTION
    assert provider.is_production_trusted
    unit = normalize_embedding([3.0, 4.0])
    assert abs(unit[0] - 0.6) < 1e-9
    emb = provider.extract(_synthetic_tone(3))
    assert len(emb) == 192
    assert abs(math.sqrt(sum(v * v for v in emb)) - 1.0) < 1e-5
    engine = SpeakerVerificationEngine(
        VerificationConfig(require_production_trust=True, allow_dev_fallback_identity=False)
    )
    assert engine._provider_or_default().provider_id == "ecapa"  # noqa: SLF001
    _ = store


def test_production_trust_rejects_histogram(monkeypatch, tmp_path: Path):
    _activate_production_env(monkeypatch, tmp_path)
    assert resolve_biometric_trust_mode() == BiometricTrustMode.PRODUCTION
    hist = HistogramEmbeddingProvider()
    assert hist.capabilities.trust_level == EmbeddingTrustLevel.DEVELOPMENT_FALLBACK
    assert not hist.is_production_trusted
    engine = SpeakerVerificationEngine(
        VerificationConfig(require_production_trust=True, allow_dev_fallback_identity=False),
        provider=hist,
    )
    result = engine.verify(
        probe_embedding=[0.1] * hist.dimension,
        enrolled={"Nolan": [[0.1] * hist.dimension]},
    )
    assert result.decision == VerificationDecision.UNTRUSTED_BACKEND
    assert not result.production_trusted


def test_claimed_vs_verified_identity():
    boundary = IdentitySecurityBoundary()
    claimed = boundary.evaluate_assertion(IdentityAssertionKind.CLAIMED_IDENTITY)
    assert claimed.assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY
    assert claimed.is_biometrically_verified is False
    assert claimed.may_access_personal_memory is False
    assert (
        voice_identity_may_access_personal_memory(
            assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY
        )
        is False
    )


def test_aes_gcm_profile_storage(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    storage = build_embedding_storage(prefer_encryption=True)
    assert isinstance(storage, AesGcmEmbeddingStorage)
    assert storage.health_dict()["using_dev_key"] is False
    payload = wrap_profile_embeddings(
        profile_id="p1",
        user_id="Nolan",
        embedding_version="ecapa_v1",
        embeddings=[[0.2, 0.4, 0.4]],
        backend=storage,
    )
    assert payload["encrypted"] is True
    assert payload.get("vectors") == []
    assert "ciphertext_b64" in payload
    assert "nonce_b64" in payload
    bundle = unwrap_profile_embeddings(payload, backend=storage)
    assert bundle == [[0.2, 0.4, 0.4]]
    health = store.storage_health()
    assert health["encryption_enabled"] is True
    assert health["using_dev_key"] is False


def test_consent_required_and_cross_user_protection(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(require_consent=True, min_sample_count=3, min_quality_score=0.1),
        temp_dir=tmp_path / "tmp",
    )
    with pytest.raises(VoiceEnrollmentError) as cross:
        service.start_enrollment(
            target_user="Nolan",
            authenticated_user="Ibrahim",
            consent_accepted=True,
        )
    assert cross.value.code == "unauthorized_target_mismatch"

    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=False,
    )
    sid = started["session"]["session_id"]
    assert started["session"].get("consent_given") is False
    with pytest.raises(VoiceEnrollmentError) as blocked:
        service.submit_sample(
            session_id=sid,
            audio_bytes=_synthetic_tone(1),
            authenticated_user="Nolan",
        )
    assert blocked.value.code in {"consent_required", "invalid_state"}

    # Explicit consent_accepted=True (Web Continuer path) unlocks collection.
    consented = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
        replace_existing=True,
    )
    assert consented["session"].get("consent_given") is True
    status = consented["session"]["status"]
    assert status == "COLLECTING" or getattr(status, "value", status) == "COLLECTING"
    assert store.get_active_profile("Nolan") is None


def test_grant_consent_api_unlocks_samples(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(require_consent=True, min_sample_count=3, min_quality_score=0.1),
        temp_dir=tmp_path / "tmp",
    )
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=False,
    )
    sid = started["session"]["session_id"]
    granted = service.grant_consent(
        session_id=sid,
        authenticated_user="Nolan",
        accepted=True,
        locale="fr-FR",
    )
    assert granted.get("accepted") is True or granted["session"].get("consent_given") is True
    assert granted["session"].get("consent_given") is True
    # Still unenrolled — no embeddings until samples are accepted + verified.
    assert store.get_active_profile("Nolan") is None


def test_separate_nolan_ibrahim_slots(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    report = run_enrollment_preflight(
        store=store, force_ecapa_load=False, reset_registry=False
    )
    nolan = report["checks"]["nolan_profile_slot"]
    ibrahim = report["checks"]["ibrahim_profile_slot"]
    assert nolan["status"] == PreflightStatus.READY.value
    assert ibrahim["status"] == PreflightStatus.READY.value
    assert nolan["details"]["biometric_enrolled"] is False
    assert ibrahim["details"]["biometric_enrolled"] is False


def test_enrollment_cancel_and_recovery(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(require_consent=True, min_sample_count=3),
        temp_dir=tmp_path / "tmp",
    )
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
    )
    sid = started["session"]["session_id"]
    cancelled = service.cancel_enrollment(session_id=sid, authenticated_user="Nolan")
    assert cancelled.get("cancelled") is True
    assert cancelled.get("session", {}).get("status") == "CANCELLED"

    again = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
    )
    assert again["session"]["session_id"] != sid


def test_duplicate_cross_user_sample_blocked(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(
            require_consent=True,
            min_sample_count=2,
            min_quality_score=0.05,
            max_sample_count=8,
        ),
        temp_dir=tmp_path / "tmp",
    )
    nolan = service.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    audio = _synthetic_tone(11, n=24000)
    service.submit_sample(
        session_id=nolan["session"]["session_id"],
        audio_bytes=audio,
        authenticated_user="Nolan",
    )
    with pytest.raises(VoiceEnrollmentError):
        service.submit_sample(
            session_id=nolan["session"]["session_id"],
            audio_bytes=_synthetic_tone(12, n=24000),
            authenticated_user="Ibrahim",
        )


def test_microphone_preflight_and_full_report(monkeypatch, tmp_path: Path):
    store = _activate_production_env(monkeypatch, tmp_path)
    # Ensure lazy ECAPA with inference stub is considered ready without model load.
    get_embedding_provider().ensure_loaded()  # type: ignore[attr-defined]
    report = run_enrollment_preflight(
        store=store, force_ecapa_load=False, reset_registry=False
    )
    assert report["records_biometric_samples"] is False
    assert report["checks"]["microphone"]["status"] == PreflightStatus.READY.value
    assert report["checks"]["consent_workflow"]["status"] == PreflightStatus.READY.value
    assert report["checks"]["aes_gcm"]["status"] == PreflightStatus.READY.value
    assert report["checks"]["production_trust"]["status"] == PreflightStatus.READY.value
    assert report["checks"]["ecapa_provider"]["status"] == PreflightStatus.READY.value
    assert report["checks"]["enrollment_storage"]["status"] == PreflightStatus.READY.value
    assert report["ok"] is True
    assert report["ready_for_real_enrollment"] is True
    assert report["enrollment_method"]["primary"] == "web_app_voice_panel"


def test_spoken_claim_does_not_verify(monkeypatch, tmp_path: Path):
    _activate_production_env(monkeypatch, tmp_path)
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "legacy.json",
        profile_store=SpeakerProfileStore(file_path=tmp_path / "profiles.json"),
        enabled=True,
    )
    result = identifier.confirm_from_text("Je suis Nolan")
    assert result.identity == SpeakerIdentity.NOLAN
    assert result.assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY
    assert result.is_claimed_only
    assert not result.is_biometrically_verified
    assert (
        voice_identity_may_access_personal_memory(
            assertion_kind=result.assertion_kind
        )
        is False
    )


def test_ensure_storage_key_script(tmp_path: Path):
    import importlib.util

    mod_path = Path(__file__).resolve().parents[1] / "scripts" / "ensure_voice_embedding_storage_key.py"
    spec = importlib.util.spec_from_file_location("ensure_key", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=dummy\n", encoding="utf-8")
    first = mod.ensure_storage_key(env_path=env)
    assert first["ok"] is True
    assert first["key_printed"] is False
    text = env.read_text(encoding="utf-8")
    assert "TITAN_VOICE_EMBEDDING_STORAGE_KEY=" in text
    second = mod.ensure_storage_key(env_path=env)
    assert second["action"] == "unchanged"


def test_web_enrollment_preflight_wired():
    root = Path(__file__).resolve().parents[1]
    api = (root / "web" / "v2" / "voice" / "voice-api.js").read_text(encoding="utf-8")
    ui = (root / "web" / "v2" / "voice" / "enrollment-ui.js").read_text(encoding="utf-8")
    routes = (root / "api" / "voice_enrollment_routes.py").read_text(encoding="utf-8")
    assert "/voice/enrollment/preflight" in api
    assert "getEnrollmentPreflight" in api
    assert "refreshPreflight" in ui
    assert "tdl-v2-voice-preflight" in ui
    assert "/preflight" in routes


def test_parse_spoken_identity_is_claim_only():
    from voice.speaker_identifier import parse_spoken_identity

    assert parse_spoken_identity("Je suis Nolan") == "Nolan"
    assert parse_spoken_identity("je suis ibrahim") == "Ibrahim"
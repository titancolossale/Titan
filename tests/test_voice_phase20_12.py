# =====================================
# Titan Phase 20.12 — Real Speaker Biometric Backend
# =====================================

"""Tests for real ECAPA/Resemblyzer adapters, trust modes, AES-GCM, identity."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import pytest

from api.readiness import build_readiness_payload
from voice.audio_prep import floats_to_pcm16_wav
from voice.biometric_trust import (
    BiometricTrustMode,
    biometric_trust_diagnostics,
    production_verification_defaults,
    resolve_biometric_trust_mode,
)
from voice.ecapa_provider import (
    EcapaEmbeddingProvider,
    ProviderInitStatus,
    normalize_embedding,
    probe_ecapa_dependencies,
)
from voice.embedding_capabilities import EmbeddingTrustLevel
from voice.embedding_diagnostics import (
    collect_biometric_readiness,
    collect_embedding_security_diagnostics,
)
from voice.embedding_provider import (
    DeterministicLocalEmbeddingProvider,
    HistogramEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    get_embedding_registry,
    reset_embedding_registry_for_tests,
    set_embedding_provider,
)
from voice.embedding_storage import (
    AesGcmEmbeddingStorage,
    EmbeddingCorruptionError,
    EnvelopeEmbeddingStorage,
    LegacyXorEnvelopeStorage,
    PlaintextEmbeddingStorage,
    unwrap_profile_embeddings,
    wrap_profile_embeddings,
)
from voice.identity_security import (
    IdentityActionClass,
    IdentityAssertionKind,
    IdentitySecurityBoundary,
    voice_identity_may_access_personal_memory,
)
from voice.resemblyzer_provider import (
    ResemblyzerEmbeddingProvider,
    probe_resemblyzer_dependencies,
)
from voice.speaker_identifier import SpeakerIdentifier, SpeakerIdentity
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    VerificationConfig,
    VerificationDecision,
)


def _synthetic_tone(seed: int, n: int = 16000, rate: int = 16000) -> bytes:
    """Synthetic PCM16 WAV — never a real Nolan/Ibrahim recording."""
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
    return values


@pytest.fixture(autouse=True)
def _reset_registries(monkeypatch):
    monkeypatch.delenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", raising=False)
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_PROVIDER", raising=False)
    reset_embedding_registry_for_tests()
    set_embedding_provider(None)
    yield
    reset_embedding_registry_for_tests()
    set_embedding_provider(None)


# --- Real provider adapter ------------------------------------------------


def test_ecapa_adapter_with_injected_inference():
    provider = EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference)
    assert provider.is_available
    assert provider.is_production_trusted
    assert provider.capabilities.trust_level == EmbeddingTrustLevel.PRODUCTION
    assert provider.dimension == 192
    a = provider.extract(_synthetic_tone(1))
    b = provider.extract(_synthetic_tone(1))
    c = provider.extract(_synthetic_tone(9))
    assert len(a) == 192
    assert a == b
    assert abs(math.sqrt(sum(v * v for v in a)) - 1.0) < 1e-6
    assert cosine_similarity(a, c) < 0.999
    provider.ensure_loaded()
    assert provider.init_status == ProviderInitStatus.READY


def test_normalization_helper():
    normed = normalize_embedding([3.0, 4.0])
    assert abs(normed[0] - 0.6) < 1e-9
    assert abs(normed[1] - 0.8) < 1e-9
    assert normalize_embedding([]) == []


def test_resemblyzer_adapter_injected():
    def _fn(audio: bytes) -> list[float]:
        digest = hashlib.md5(audio).digest()
        vals = [(b / 127.5) - 1.0 for b in (digest * 16)][:256]
        return vals

    provider = ResemblyzerEmbeddingProvider(inference_fn=_fn)
    assert provider.is_available
    assert provider.is_production_trusted
    emb = provider.extract(_synthetic_tone(3))
    assert len(emb) == 256
    assert abs(math.sqrt(sum(v * v for v in emb)) - 1.0) < 1e-5


def test_provider_unavailable_without_deps():
    ecapa = EcapaEmbeddingProvider(force_available=False)
    assert not ecapa.is_available
    assert ecapa.init_status == ProviderInitStatus.UNAVAILABLE
    with pytest.raises(Exception):
        ecapa.ensure_loaded()
    with pytest.raises(Exception):
        ecapa.extract(_synthetic_tone(1))


def test_model_initialization_failure():
    def _boom(_audio: bytes) -> list[float]:
        raise RuntimeError("model_broken")

    # force_available with failing ensure via custom path: inference_fn raises
    provider = EcapaEmbeddingProvider(inference_fn=_boom)
    with pytest.raises(Exception):
        provider.extract(_synthetic_tone(2))


def test_lazy_loading_status():
    provider = EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference)
    assert provider.init_status in {
        ProviderInitStatus.NOT_LOADED,
        ProviderInitStatus.READY,
    }
    provider.extract(_synthetic_tone(4))
    assert provider.init_status == ProviderInitStatus.READY
    health = provider.health_dict()
    assert health["lazy_load"] is True
    assert health["deterministic_inference"] is True
    assert health["model_version"]


def test_probe_dependencies_safe():
    ecapa = probe_ecapa_dependencies()
    assert "available" in ecapa
    assert "model_source" in ecapa
    assert "torch" in ecapa
    assert "torchaudio" in ecapa
    assert "speechbrain" in ecapa
    rz = probe_resemblyzer_dependencies()
    assert "available" in rz


def test_ecapa_local_strategy_windows_defaults_to_copy(monkeypatch):
    """Windows hosts often lack symlink privilege — COPY must be the default."""
    import os as os_mod

    from speechbrain.utils.fetching import LocalStrategy

    monkeypatch.delenv("TITAN_VOICE_ECAPA_LOCAL_STRATEGY", raising=False)
    provider = EcapaEmbeddingProvider(force_available=True, inference_fn=_fake_ecapa_inference)
    monkeypatch.setattr(os_mod, "name", "nt")
    strategy = provider._resolve_local_strategy()
    assert strategy == LocalStrategy.COPY
    monkeypatch.setenv("TITAN_VOICE_ECAPA_LOCAL_STRATEGY", "symlink")
    assert provider._resolve_local_strategy() == LocalStrategy.SYMLINK


# --- Trust separation -----------------------------------------------------


def test_development_vs_production_trust(monkeypatch):
    monkeypatch.setenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "development")
    assert resolve_biometric_trust_mode() == BiometricTrustMode.DEVELOPMENT
    dev = production_verification_defaults()
    assert dev["allow_dev_fallback_identity"] is True
    assert dev["require_production_trust"] is False

    monkeypatch.setenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "production")
    assert resolve_biometric_trust_mode() == BiometricTrustMode.PRODUCTION
    prod = production_verification_defaults()
    assert prod["require_production_trust"] is True
    assert prod["allow_dev_fallback_identity"] is False


def test_histogram_production_rejection():
    set_embedding_provider(HistogramEmbeddingProvider())
    engine = SpeakerVerificationEngine(
        VerificationConfig(
            require_production_trust=True,
            allow_dev_fallback_identity=False,
        )
    )
    probe = HistogramEmbeddingProvider().extract(_synthetic_tone(5))
    result = engine.verify(
        probe_embedding=probe,
        enrolled={"Nolan": [probe]},
    )
    assert result.decision == VerificationDecision.UNTRUSTED_BACKEND
    assert not result.is_verified


def test_production_trust_diag():
    diag = biometric_trust_diagnostics(BiometricTrustMode.PRODUCTION)
    assert diag["production_rejects_histogram_trust"] is True
    assert diag["histogram_allowed_for_trusted_identity"] is False


# --- Verification pipeline ------------------------------------------------


def test_verified_unknown_ambiguous_threshold():
    provider = EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference)
    set_embedding_provider(provider)
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.95, medium_threshold=0.4, ambiguity_delta=0.05),
        provider=provider,
    )
    emb_a = [provider.extract(_synthetic_tone(10)), provider.extract(_synthetic_tone(10))]
    emb_b = [provider.extract(_synthetic_tone(20)), provider.extract(_synthetic_tone(20))]
    probe = provider.extract(_synthetic_tone(10))
    verified = engine.verify(
        probe_embedding=probe,
        enrolled={"Nolan": emb_a, "Ibrahim": emb_b},
        profile_versions={
            "Nolan": provider.embedding_version,
            "Ibrahim": provider.embedding_version,
        },
    )
    assert verified.decision == VerificationDecision.VERIFIED
    assert verified.matched_user == "Nolan"
    assert verified.is_verified

    unknown = engine.verify(
        probe_embedding=provider.extract(_synthetic_tone(77)),
        enrolled={"Nolan": emb_a},
        profile_versions={"Nolan": provider.embedding_version},
    )
    assert unknown.decision in {
        VerificationDecision.UNKNOWN,
        VerificationDecision.REJECTED,
    }

    # Cross-user equal scores → AMBIGUOUS
    same = [provider.extract(_synthetic_tone(10))]
    amb = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.5, medium_threshold=0.3, ambiguity_delta=1.0),
        provider=provider,
    ).verify(
        probe_embedding=same[0],
        enrolled={"Nolan": same, "Ibrahim": same},
        profile_versions={
            "Nolan": provider.embedding_version,
            "Ibrahim": provider.embedding_version,
        },
    )
    assert amb.decision == VerificationDecision.AMBIGUOUS
    assert amb.matched_user is None


def test_cross_user_rejection_on_expected():
    provider = EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference)
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.9, medium_threshold=0.4),
        provider=provider,
    )
    nolan = [provider.extract(_synthetic_tone(1))]
    ibrahim = [provider.extract(_synthetic_tone(2))]
    result = engine.verify(
        probe_embedding=provider.extract(_synthetic_tone(2)),
        enrolled={"Nolan": nolan, "Ibrahim": ibrahim},
        profile_versions={
            "Nolan": provider.embedding_version,
            "Ibrahim": provider.embedding_version,
        },
        expected_user_id="Nolan",
    )
    assert result.decision == VerificationDecision.AMBIGUOUS
    assert result.reason == "cross_user_ambiguous"


def test_similarity_and_threshold_boundaries():
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.8, medium_threshold=0.5)
    )
    enrolled = {"Nolan": [[1.0, 0.0]]}
    high = engine.verify(probe_embedding=[1.0, 0.0], enrolled=enrolled)
    assert high.decision == VerificationDecision.VERIFIED
    mid = engine.verify(probe_embedding=[0.6, 0.8], enrolled=enrolled)
    assert mid.decision != VerificationDecision.VERIFIED or mid.confidence >= 0.8
    low = engine.verify(probe_embedding=[0.0, 1.0], enrolled=enrolled)
    assert not low.is_verified


# --- Claimed vs verified identity -----------------------------------------


def test_claimed_vs_verified_identity():
    identifier = SpeakerIdentifier(enabled=True)
    claimed = identifier.confirm_from_text("je suis Nolan")
    assert claimed.is_known
    assert claimed.is_claimed_only
    assert not claimed.is_biometrically_verified
    assert claimed.assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY
    assert claimed.reason == "explicit_confirmation_claimed"
    assert not identifier.may_access_personal_memory(claimed)

    boundary = IdentitySecurityBoundary()
    decision = boundary.evaluate_assertion(IdentityAssertionKind.CLAIMED_IDENTITY)
    assert decision.may_bind_user_context is True
    assert decision.may_access_personal_memory is False
    assert decision.is_biometrically_verified is False

    assert voice_identity_may_access_personal_memory(
        assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY
    ) is False
    assert voice_identity_may_access_personal_memory(
        assertion_kind=IdentityAssertionKind.VERIFIED_IDENTITY
    ) is True

    for action in (
        IdentityActionClass.DESTRUCTIVE,
        IdentityActionClass.FINANCIAL,
        IdentityActionClass.AUTHENTICATION,
    ):
        assert not boundary.evaluate_action(
            action, assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY
        ).allowed


def test_spoken_claim_does_not_auto_verify():
    claimed = SpeakerIdentifier().confirm_from_text("I am Ibrahim")
    assert claimed.identity == SpeakerIdentity.IBRAHIM
    assert claimed.assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY
    assert claimed.to_dict()["is_biometrically_verified"] is False


# --- AES-GCM storage ------------------------------------------------------


def test_aes_gcm_roundtrip_and_metadata():
    backend = AesGcmEmbeddingStorage(key=b"0123456789abcdef0123456789abcdef", key_id="k1")
    encoded = wrap_profile_embeddings(
        profile_id="bio1",
        user_id="Nolan",
        embedding_version="ecapa_v1",
        embeddings=[[0.1] * 8, [0.2] * 8],
        backend=backend,
    )
    assert encoded["codec"] == "aes_gcm_v1"
    assert encoded["envelope_version"] == 2
    assert encoded["key_id"] == "k1"
    assert encoded["vectors"] == []
    assert "nonce_b64" in encoded
    decoded = unwrap_profile_embeddings(encoded, backend=backend)
    assert decoded == [[0.1] * 8, [0.2] * 8]
    health = backend.health_dict()
    assert health["algorithm"] == "AES-256-GCM"
    assert health["key_id"] == "k1"
    assert health["envelope_version"] == 2


def test_aes_gcm_tamper_detection():
    backend = AesGcmEmbeddingStorage(key=b"tamper-key-32-bytes-xxxxxxxxxxxx")
    encoded = wrap_profile_embeddings(
        profile_id="bio2",
        user_id="Ibrahim",
        embedding_version="ecapa_v1",
        embeddings=[[0.5, 0.5]],
        backend=backend,
    )
    nonce = bytearray(encoded["nonce_b64"].encode("ascii"))
    nonce[-1] = ord("0") if nonce[-1] != ord("0") else ord("1")
    encoded["nonce_b64"] = nonce.decode("ascii")
    with pytest.raises(EmbeddingCorruptionError):
        unwrap_profile_embeddings(encoded, backend=backend)


def test_legacy_xor_migration_to_aes_gcm():
    legacy_key = hashlib.sha256(b"titan-voice-embedding-dev-key").digest()
    # Craft a legacy XOR envelope manually via LegacyXor path internals.
    from voice.embedding_storage import StoredEmbeddingBundle
    import base64
    import hmac
    import json

    bundle = StoredEmbeddingBundle(
        profile_id="legacy1",
        user_id="Nolan",
        embedding_version="local_det_v1",
        vectors=[[0.9, 0.1]],
        format_version=1,
    ).seal()
    raw = json.dumps(bundle.vectors, separators=(",", ":")).encode("utf-8")
    cipher = bytes(b ^ legacy_key[i % len(legacy_key)] for i, b in enumerate(raw))
    mac = hmac.new(legacy_key, cipher, hashlib.sha256).hexdigest()
    legacy_payload = {
        "profile_id": bundle.profile_id,
        "user_id": bundle.user_id,
        "embedding_version": bundle.embedding_version,
        "vectors": [],
        "ciphertext_b64": base64.b64encode(cipher).decode("ascii"),
        "mac": mac,
        "codec": "encrypted_envelope",
        "integrity_hash": bundle.integrity_hash,
        "format_version": 1,
        "encrypted": True,
        "envelope_version": 1,
    }
    aes = AesGcmEmbeddingStorage(allow_legacy_xor_decode=True)
    vectors = aes.decode(legacy_payload).vectors
    assert vectors == [[0.9, 0.1]]
    assert aes.health_dict()["legacy_migrations_observed"] >= 1


# --- Diagnostics & readiness ----------------------------------------------


def test_diagnostics_safe_no_embeddings():
    set_embedding_provider(EcapaEmbeddingProvider(inference_fn=_fake_ecapa_inference))
    snap = collect_embedding_security_diagnostics()
    blob = str(snap)
    assert "embedding_provider" in snap
    assert "trust_mode" in snap
    assert "verification_threshold" in snap["verification"]
    assert "envelope_version" in snap["storage"] or snap["storage"].get("codec")
    assert "[[0." not in blob
    assert "0.1, 0.2" not in blob
    readiness = collect_biometric_readiness()
    assert readiness["required"] is False
    assert readiness["affects_ready"] is False


def test_railway_safe_readiness_ignores_missing_biometric(monkeypatch):
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    payload = build_readiness_payload()
    assert "voice_biometric" in payload["checks"]
    assert payload["checks"]["voice_biometric"]["required"] is False
    assert payload["checks"]["voice_biometric"]["affects_ready"] is False
    # Core readiness must not flip solely because biometric deps are missing.
    assert payload["checks"]["voice_biometric"]["ok"] is True


def test_registry_lists_real_providers():
    registry = get_embedding_registry()
    ids = {p["provider_id"] for p in registry.list_providers()}
    assert "ecapa" in ids
    assert "resemblyzer" in ids
    assert "histogram" in ids

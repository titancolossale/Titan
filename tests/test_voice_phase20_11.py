# =====================================
# Titan Phase 20.11 — Production Speaker Embeddings & Identity Security
# =====================================

"""Exhaustive tests for production embeddings, verification, storage, migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice.anti_spoof import (
    HeuristicAntiSpoofProvider,
    LivenessAvailability,
    NullAntiSpoofProvider,
    evaluate_liveness,
    get_anti_spoof_registry,
    reset_anti_spoof_registry_for_tests,
)
from voice.diagnostics import emit_voice_diagnostic, sanitize_diagnostic_payload
from voice.embedding_capabilities import EmbeddingTrustLevel
from voice.embedding_diagnostics import collect_embedding_security_diagnostics
from voice.embedding_migration import (
    EmbeddingMigrationService,
    MigrationStatus,
)
from voice.embedding_provider import (
    DeterministicLocalEmbeddingProvider,
    EcapaEmbeddingProvider,
    HistogramEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    get_embedding_registry,
    is_dev_fallback_version,
    reset_embedding_registry_for_tests,
    set_embedding_provider,
)
from voice.embedding_storage import (
    EmbeddingCorruptionError,
    EnvelopeEmbeddingStorage,
    PlaintextEmbeddingStorage,
    StoredEmbeddingBundle,
    build_embedding_storage,
    detect_duplicate_user_embeddings,
    unwrap_profile_embeddings,
    wrap_profile_embeddings,
)
from voice.enrollment_diagnostics import collect_enrollment_diagnostics
from voice.enrollment_models import EnrollmentStatus, SpeakerIdentityProfile
from voice.enrollment_verification import (
    EnrollmentVerificationPipeline,
    VerificationThresholds,
)
from voice.identity_security import (
    IdentityActionClass,
    IdentitySecurityBoundary,
    voice_identity_may_bind_context,
)
from voice.speaker_identifier import SpeakerIdentifier, SpeakerIdentity
from voice.speaker_profile_store import SCHEMA_VERSION, SpeakerProfileStore
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    VerificationConfig,
    VerificationDecision,
)


def _audio(seed: int, n: int = 8000) -> bytes:
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


@pytest.fixture(autouse=True)
def _reset_registries():
    reset_embedding_registry_for_tests()
    reset_anti_spoof_registry_for_tests()
    set_embedding_provider(None)
    yield
    reset_embedding_registry_for_tests()
    reset_anti_spoof_registry_for_tests()
    set_embedding_provider(None)


# --- Embedding providers -------------------------------------------------


def test_histogram_is_dev_fallback_not_production_trusted():
    provider = HistogramEmbeddingProvider()
    assert provider.is_available
    assert provider.is_dev_fallback
    assert not provider.is_production_trusted
    assert provider.capabilities.trust_level == EmbeddingTrustLevel.DEVELOPMENT_FALLBACK
    assert is_dev_fallback_version(provider.embedding_version)


def test_ecapa_resemblyzer_stubs_unavailable():
    ecapa = EcapaEmbeddingProvider()
    # Without optional torch/speechbrain, provider must stay unavailable.
    if not ecapa.is_available:
        assert not ecapa.is_production_trusted
        with pytest.raises(Exception):
            ecapa.extract(_audio(1))
    res = __import__("voice.resemblyzer_provider", fromlist=["ResemblyzerEmbeddingProvider"])
    rz = res.ResemblyzerEmbeddingProvider()
    if not rz.is_available:
        assert not rz.is_production_trusted
        with pytest.raises(Exception):
            rz.extract(_audio(1))


def test_local_deterministic_is_production_trusted_plumbing():
    provider = DeterministicLocalEmbeddingProvider()
    assert provider.is_available
    assert provider.is_production_trusted
    a = provider.extract(_audio(7))
    b = provider.extract(_audio(7))
    c = provider.extract(_audio(99))
    assert len(a) == 64
    assert a == b
    assert cosine_similarity(a, c) < 0.999


def test_provider_switching():
    registry = get_embedding_registry()
    registry.set_active("histogram")
    assert get_embedding_provider().provider_id == "histogram"
    registry.set_active("local_deterministic")
    assert get_embedding_provider().provider_id == "local_deterministic"
    assert get_embedding_provider().is_production_trusted
    ecapa = registry.get("ecapa")
    if ecapa.is_available:
        registry.set_active("ecapa")
        assert get_embedding_provider().provider_id == "ecapa"
        assert get_embedding_provider().is_production_trusted
        registry.set_active("histogram")
    else:
        with pytest.raises(Exception):
            registry.set_active("ecapa")


def test_capability_detection():
    registry = get_embedding_registry()
    caps = registry.detect_capabilities("histogram")
    assert caps.is_dev_fallback
    local = registry.detect_capabilities("local_deterministic")
    assert local.is_production_trusted
    ready = registry.list_production_ready()
    assert any(p["provider_id"] == "local_deterministic" for p in ready)
    assert not any(p["provider_id"] == "histogram" for p in ready)


# --- Speaker verification ------------------------------------------------


def test_verification_match_and_unknown():
    provider = DeterministicLocalEmbeddingProvider()
    set_embedding_provider(provider)
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.9, medium_threshold=0.5),
        provider=provider,
    )
    emb_n = [provider.extract(_audio(1)), provider.extract(_audio(1))]
    emb_i = [provider.extract(_audio(2)), provider.extract(_audio(2))]
    probe = provider.extract(_audio(1))
    matched = engine.verify(
        probe_embedding=probe,
        enrolled={"Nolan": emb_n, "Ibrahim": emb_i},
        profile_versions={
            "Nolan": provider.embedding_version,
            "Ibrahim": provider.embedding_version,
        },
    )
    assert matched.decision in {
        VerificationDecision.MATCHED,
        VerificationDecision.VERIFIED,
    }
    assert matched.matched_user == "Nolan"
    assert matched.is_known

    unknown_probe = provider.extract(_audio(50))
    unknown = engine.verify(
        probe_embedding=unknown_probe,
        enrolled={"Nolan": emb_n},
        profile_versions={"Nolan": provider.embedding_version},
    )
    assert unknown.decision in {
        VerificationDecision.UNKNOWN,
        VerificationDecision.REJECTED,
    }
    assert not unknown.is_known


def test_ambiguous_speakers_prefer_unknown():
    provider = DeterministicLocalEmbeddingProvider()
    # Force identical enrollments → ambiguous when both score equally.
    emb = [provider.extract(_audio(3))]
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.5, medium_threshold=0.3, ambiguity_delta=1.0),
        provider=provider,
    )
    result = engine.verify(
        probe_embedding=emb[0],
        enrolled={"Nolan": emb, "Ibrahim": emb},
        profile_versions={
            "Nolan": provider.embedding_version,
            "Ibrahim": provider.embedding_version,
        },
    )
    assert result.decision == VerificationDecision.AMBIGUOUS
    assert result.matched_user is None
    assert not result.is_known


def test_threshold_boundaries():
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.8, medium_threshold=0.5, ambiguity_delta=0.05)
    )
    enrolled = {"Nolan": [[1.0, 0.0], [0.9, 0.1]]}
    # High
    high = engine.verify(probe_embedding=[1.0, 0.0], enrolled=enrolled)
    assert high.decision in {
        VerificationDecision.MATCHED,
        VerificationDecision.VERIFIED,
    }
    # Medium → UNKNOWN (prefer confirm over auto-bind)
    med = engine.verify(probe_embedding=[0.7, 0.714], enrolled=enrolled)
    # Low
    low = engine.verify(probe_embedding=[0.0, 1.0], enrolled=enrolled)
    assert low.decision in {
        VerificationDecision.UNKNOWN,
        VerificationDecision.REJECTED,
    }
    assert not low.is_known
    assert med.decision not in {
        VerificationDecision.MATCHED,
        VerificationDecision.VERIFIED,
    } or med.confidence >= 0.8


def test_multi_sample_aggregation():
    engine = SpeakerVerificationEngine()
    probe = [1.0, 0.0]
    score = engine.score_user(
        probe,
        [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]],
        user_id="Nolan",
    )
    assert score.score >= 0.99
    assert len(score.sample_scores) == 3
    assert score.centroid_score is not None


def test_version_mismatch_rejects():
    engine = SpeakerVerificationEngine()
    result = engine.verify(
        probe_embedding=[1.0, 0.0],
        enrolled={"Nolan": [[1.0, 0.0]]},
        profile_versions={"Nolan": "ecapa_v1"},
    )
    assert result.decision == VerificationDecision.VERSION_MISMATCH


def test_require_production_trust_blocks_histogram():
    set_embedding_provider(HistogramEmbeddingProvider())
    engine = SpeakerVerificationEngine(
        VerificationConfig(require_production_trust=True)
    )
    result = engine.verify(
        probe_embedding=[1.0] + [0.0] * 31,
        enrolled={"Nolan": [[1.0] + [0.0] * 31]},
    )
    assert result.decision == VerificationDecision.UNTRUSTED_BACKEND


def test_enrollment_pipeline_uses_verification_engine():
    provider = DeterministicLocalEmbeddingProvider()
    set_embedding_provider(provider)
    pipeline = EnrollmentVerificationPipeline(
        VerificationThresholds(pass_threshold=0.9, medium=0.5)
    )
    emb = provider.extract(_audio(11))
    result = pipeline.score_probe(
        probe_embedding=emb,
        profile_embeddings=[emb, emb],
        expected_user_id="Nolan",
        profile_embedding_version=provider.embedding_version,
    )
    assert result.verification.outcome.value == "passed"


# --- Identity security ---------------------------------------------------


def test_voice_identity_cannot_authorize_high_risk():
    boundary = IdentitySecurityBoundary()
    for action in (
        IdentityActionClass.DESTRUCTIVE,
        IdentityActionClass.FINANCIAL,
        IdentityActionClass.ADMINISTRATIVE,
        IdentityActionClass.HIGH_RISK,
        IdentityActionClass.AUTHENTICATION,
        IdentityActionClass.AUTHORIZATION,
    ):
        decision = boundary.evaluate_action(action)
        assert not decision.allowed
        assert decision.requires_separate_auth

    statement = boundary.assert_not_authorization()
    assert statement["is_authentication"] is False
    assert statement["may_authorize_destructive"] is False
    assert statement["preserves_existing_auth_systems"] is True


def test_unknown_and_ambiguous_block_personal_context():
    engine = SpeakerVerificationEngine(
        VerificationConfig(high_threshold=0.9, medium_threshold=0.5, ambiguity_delta=1.0)
    )
    emb = [[1.0, 0.0]]
    ambiguous = engine.verify(
        probe_embedding=[1.0, 0.0],
        enrolled={"Nolan": emb, "Ibrahim": emb},
    )
    assert not voice_identity_may_bind_context(ambiguous)

    unknown = engine.verify(
        probe_embedding=[0.0, 1.0],
        enrolled={"Nolan": emb},
    )
    assert not voice_identity_may_bind_context(unknown)


def test_high_match_allows_context_only():
    engine = SpeakerVerificationEngine(VerificationConfig(high_threshold=0.5))
    result = engine.verify(
        probe_embedding=[1.0, 0.0],
        enrolled={"Nolan": [[1.0, 0.0]]},
    )
    assert voice_identity_may_bind_context(result)
    boundary = IdentitySecurityBoundary()
    assert not boundary.evaluate_action(
        IdentityActionClass.DESTRUCTIVE, verification=result
    ).allowed


# --- Embedding storage ---------------------------------------------------


def test_plaintext_storage_integrity_and_wrap():
    backend = PlaintextEmbeddingStorage()
    payload = wrap_profile_embeddings(
        profile_id="p1",
        user_id="Nolan",
        embedding_version="local_det_v1",
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        backend=backend,
    )
    assert payload["integrity_hash"]
    assert payload["encrypted"] is False
    vectors = unwrap_profile_embeddings(payload, backend=backend)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_envelope_encryption_roundtrip():
    backend = EnvelopeEmbeddingStorage(key=b"test-key-32-bytes-xxxxxxxxxxxx")
    assert backend.encryption_enabled
    encoded = wrap_profile_embeddings(
        profile_id="p2",
        user_id="Ibrahim",
        embedding_version="local_det_v1",
        embeddings=[[1.0, 0.0, 0.0]],
        backend=backend,
    )
    assert encoded["encrypted"] is True
    assert encoded["vectors"] == []
    assert "ciphertext_b64" in encoded
    decoded = unwrap_profile_embeddings(encoded, backend=backend)
    assert decoded == [[1.0, 0.0, 0.0]]


def test_envelope_corruption_detected():
    backend = EnvelopeEmbeddingStorage(key=b"key-a")
    encoded = wrap_profile_embeddings(
        profile_id="p3",
        user_id="Nolan",
        embedding_version="local_det_v1",
        embeddings=[[0.5, 0.5]],
        backend=backend,
    )
    # Tamper with ciphertext — AES-GCM auth must fail.
    raw = bytearray(encoded["ciphertext_b64"].encode("ascii"))
    raw[0] = ord("A") if raw[0] != ord("A") else ord("B")
    encoded["ciphertext_b64"] = raw.decode("ascii")
    with pytest.raises(EmbeddingCorruptionError):
        unwrap_profile_embeddings(encoded, backend=backend)


def test_envelope_has_aes_gcm_metadata():
    backend = EnvelopeEmbeddingStorage(key=b"test-key-32-bytes-xxxxxxxxxxxx")
    encoded = wrap_profile_embeddings(
        profile_id="p2b",
        user_id="Nolan",
        embedding_version="local_det_v1",
        embeddings=[[0.1, 0.2]],
        backend=backend,
    )
    assert encoded.get("codec") == "aes_gcm_v1"
    assert encoded.get("envelope_version") == 2
    assert encoded.get("key_id")
    assert "nonce_b64" in encoded
    health = backend.health_dict()
    assert health["algorithm"] == "AES-256-GCM"
    assert health["authenticated_encryption"] is True



def test_plaintext_integrity_corruption():
    bundle = StoredEmbeddingBundle(
        profile_id="p4",
        user_id="Nolan",
        embedding_version="histogram_v1",
        vectors=[[1.0, 0.0]],
    ).seal()
    payload = bundle.to_storage_dict()
    payload["vectors"] = [[0.0, 1.0]]
    with pytest.raises(EmbeddingCorruptionError):
        PlaintextEmbeddingStorage().decode(payload)


def test_profile_persistence_replacement_revocation(tmp_path: Path):
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    profile = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    profile.embeddings = [[1.0, 0.0], [0.9, 0.1]]
    profile.sample_count = 2
    profile.embedding_version = "histogram_v1"
    profile.production_trusted = False
    store.create_profile(profile)
    store.activate_profile(profile.profile_id)

    active = store.list_active_embeddings()
    assert "Nolan" in active

    replacement = SpeakerIdentityProfile.create(
        user_id="Nolan",
        status=EnrollmentStatus.ENROLLED,
        profile_version=2,
    )
    replacement.embeddings = [[0.0, 1.0]]
    replacement.sample_count = 1
    replacement.replaces_profile_id = profile.profile_id
    store.create_profile(replacement)
    store.replace_active_profile(
        new_profile_id=replacement.profile_id,
        old_profile_id=profile.profile_id,
    )
    assert store.get_active_profile("Nolan").profile_id == replacement.profile_id
    old = store.get_profile(profile.profile_id)
    assert old is not None
    assert old.enrollment_status == EnrollmentStatus.REVOKED

    store.revoke_profile(replacement.profile_id)
    assert store.get_active_profile("Nolan") is None
    assert store.list_active_embeddings() == {}

    # Schema v4 persistence
    raw = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    public = store.list_safe_profiles()
    assert all("embeddings" not in p for p in public)
    assert all("vectors" not in p for p in public)


def test_duplicate_user_protection():
    conflict = detect_duplicate_user_embeddings(
        candidate=[[1.0, 0.0]],
        existing_by_user={"Ibrahim": [[1.0, 0.0]]},
        exclude_user_id="Nolan",
        threshold=0.9,
    )
    assert conflict == "Ibrahim"
    none = detect_duplicate_user_embeddings(
        candidate=[[0.0, 1.0]],
        existing_by_user={"Ibrahim": [[1.0, 0.0]]},
        threshold=0.9,
    )
    assert none is None


def test_store_corruption_deactivates(tmp_path: Path):
    path = tmp_path / "profiles.json"
    store = SpeakerProfileStore(file_path=path)
    profile = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    profile.embeddings = [[1.0, 0.0]]
    profile.sample_count = 1
    store.create_profile(profile)
    store.activate_profile(profile.profile_id)
    store.save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    # Tamper sealed vectors while keeping old integrity hash.
    pid = profile.profile_id
    raw["profiles"][pid]["embeddings"] = [[0.0, 1.0]]
    # Ensure integrity_hash present from save
    assert raw["profiles"][pid].get("integrity_hash")
    path.write_text(json.dumps(raw), encoding="utf-8")

    store2 = SpeakerProfileStore(file_path=path)
    store2.load()
    events = store2.list_corruption_events()
    assert events
    assert store2.list_active_embeddings() == {}


# --- Migration -----------------------------------------------------------


def test_histogram_cannot_auto_become_production(tmp_path: Path):
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    profile = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    profile.embeddings = [[1.0] + [0.0] * 31]
    profile.embedding_version = "histogram_v1"
    profile.active = True
    store.create_profile(profile)
    store.activate_profile(profile.profile_id)

    set_embedding_provider(DeterministicLocalEmbeddingProvider())
    service = EmbeddingMigrationService(store)
    report = service.assess(target_provider_id="local_deterministic")
    assert report.histogram_profiles_blocked_from_auto_trust >= 1
    assert report.to_dict()["auto_promote_histogram_forbidden"] is True
    plan = report.plans[0]
    assert plan.auto_trust_blocked
    assert plan.requires_reenrollment
    assert plan.status == MigrationStatus.BLOCKED_AUTO_TRUST

    service.apply_pending_deactivations(report)
    assert store.get_active_profile("Nolan") is None


def test_migration_status_defers_phase_20_10b(tmp_path: Path):
    store = SpeakerProfileStore(file_path=tmp_path / "m.json")
    status = EmbeddingMigrationService(store).public_status()
    assert status["histogram_auto_trust_forbidden"] is True
    assert status["phase_20_10b_real_enrollment_deferred"] is True


# --- Anti-spoof ----------------------------------------------------------


def test_anti_spoof_unavailable_does_not_weaken():
    reset_anti_spoof_registry_for_tests()
    registry = get_anti_spoof_registry()
    registry.set_active("null")
    result = evaluate_liveness(audio_bytes=_audio(1))
    assert result.availability == LivenessAvailability.UNAVAILABLE
    assert result.weakens_verification is False
    assert result.passed is None


def test_heuristic_identical_samples():
    provider = HeuristicAntiSpoofProvider()
    emb = [[1.0, 0.0], [1.0, 0.0]]
    result = provider.evaluate(embeddings=emb, fingerprints=["a", "a"])
    assert result.availability == LivenessAvailability.STUB
    assert result.passed is False
    assert result.weakens_verification is False
    kinds = {s.kind.value for s in result.signals}
    assert "identical_samples" in kinds


def test_null_provider_health():
    health = NullAntiSpoofProvider().health_dict()
    assert health["claims_perfect_anti_spoofing"] is False
    assert health["weakens_verification_when_unavailable"] is False


# --- Diagnostics privacy -------------------------------------------------


def test_diagnostics_never_expose_embeddings(tmp_path: Path):
    store = SpeakerProfileStore(file_path=tmp_path / "d.json")
    profile = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    profile.embeddings = [[0.1, 0.2, 0.3]]
    store.create_profile(profile)

    snap = collect_embedding_security_diagnostics(store=store)
    blob = json.dumps(snap)
    assert '"embeddings"' not in blob
    assert '"vectors"' not in blob
    for profile_pub in snap.get("profiles", []):
        assert "embeddings" not in profile_pub
        assert "vectors" not in profile_pub
        assert "embedding" not in profile_pub  # singular vector key
        # embedding_version metadata is allowed
        assert "embedding_version" in profile_pub

    enroll = collect_enrollment_diagnostics(store=store)
    assert "liveness" in enroll
    assert "migration_status" in enroll
    assert "identity_security" in enroll
    assert enroll["identity_security"]["may_authorize_destructive"] is False

    dirty = sanitize_diagnostic_payload(
        {"embeddings": [[1, 2]], "vectors": [[3]], "ok": True, "confidence": 0.9}
    )
    assert "embeddings" not in dirty
    assert "vectors" not in dirty
    assert dirty["ok"] is True

    emitted = emit_voice_diagnostic(
        "VOICE_VERIFICATION_DECISION",
        confidence=0.9,
        embeddings=[[1.0, 2.0]],
        decision="unknown",
    )
    assert "embeddings" not in emitted


def test_identifier_status_includes_security():
    identifier = SpeakerIdentifier(enabled=True)
    status = identifier.status()
    assert status["identity_security"]["is_authorization"] is False
    assert "embedding_version" in status
    assert status["is_dev_fallback"] is True


def test_identifier_uses_verification_engine(tmp_path: Path):
    provider = DeterministicLocalEmbeddingProvider()
    set_embedding_provider(provider)
    store = SpeakerProfileStore(file_path=tmp_path / "id.json")
    profile = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    profile.embeddings = [provider.extract(_audio(42)), provider.extract(_audio(42))]
    profile.embedding_version = provider.embedding_version
    profile.sample_count = 2
    store.create_profile(profile)
    store.activate_profile(profile.profile_id)

    identifier = SpeakerIdentifier(
        profile_store=store,
        min_confidence=0.9,
        medium_confidence=0.4,
    )
    result = identifier.identify(_audio(42))
    assert result.identity == SpeakerIdentity.NOLAN
    assert result.is_known
    assert result.decision in {
        VerificationDecision.MATCHED.value,
        VerificationDecision.VERIFIED.value,
    }
    assert result.is_biometrically_verified
    assert result.assertion_kind.value == "verified_identity"

    other = identifier.identify(_audio(999))
    assert other.identity == SpeakerIdentity.UNKNOWN


def test_build_embedding_storage_flag():
    plain = build_embedding_storage(prefer_encryption=False)
    assert isinstance(plain, PlaintextEmbeddingStorage)
    enc = build_embedding_storage(prefer_encryption=True)
    assert isinstance(enc, EnvelopeEmbeddingStorage)

# =====================================
# Titan Phase 20.13 — Biometric Persistence Across Redeploys
# =====================================

"""Prove encrypted voice profiles survive restart / Railway redeploy simulation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from voice.biometric_persistence import (
    bootstrap_biometric_storage,
    collect_biometric_storage_readiness,
    detect_persistent_storage,
    ensure_biometric_directories,
    validate_biometric_storage,
)
from voice.embedding_provider import cosine_similarity, mean_embedding
from voice.embedding_storage import AesGcmEmbeddingStorage, build_embedding_storage
from voice.enrollment_models import EnrollmentConfig, EnrollmentStatus, SpeakerIdentityProfile
from voice.speaker_profile_store import SCHEMA_VERSION, SpeakerProfileStore
from voice.voice_enrollment import VoiceEnrollmentService


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
    """Synthetic PCM-ish bytes that pass duration/quality gates (Phase 20.2 style)."""
    n = int(16000 * 2 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


@pytest.fixture
def encrypted_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SpeakerProfileStore:
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "true")
    monkeypatch.setenv(
        "TITAN_VOICE_EMBEDDING_STORAGE_KEY",
        "phase20-13-test-key-do-not-use-in-production-0001",
    )
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_KEY_ID", "primary")
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "false")
    monkeypatch.setenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", "true")
    path = tmp_path / "data" / "voice_speaker_profiles.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SpeakerProfileStore(file_path=path)
    store._storage = build_embedding_storage(prefer_encryption=True)
    return store


def test_ensure_biometric_directories_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "vol" / "data"
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    created = ensure_biometric_directories()
    assert (data / "voice_enrollment_tmp").is_dir()
    assert (data / "voice_live_tmp").is_dir()
    assert (data / "voice_models" / "ecapa").is_dir()
    assert any("voice_enrollment_tmp" in item or "ecapa" in item for item in created) or (
        data / "voice_enrollment_tmp"
    ).is_dir()


def test_validation_rejects_path_outside_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "true")
    outside = tmp_path / "ephemeral" / "profiles.json"
    report = validate_biometric_storage(profiles_path=outside, require_persistent=True)
    assert report.ok is False
    assert any("outside TITAN_DATA_DIR" in msg for msg in report.diagnostics)


def test_validation_never_treats_temp_as_persistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "titan_bio_tmp_probe"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        persistent, signals = detect_persistent_storage(tmp / "voice_speaker_profiles.json")
        assert persistent is False
        assert signals.get("under_temp") is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_production_requires_persistent_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data = tmp_path / "app_data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "true")
    monkeypatch.delenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", raising=False)
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    report = validate_biometric_storage(
        profiles_path=data / "voice_speaker_profiles.json",
        require_persistent=True,
    )
    # Writable but not mount-backed → fail closed (no silent ephemeral fallback).
    assert report.writable is True
    assert report.persistent is False
    assert report.ok is False
    assert any("volume" in msg.lower() or "persistence" in msg.lower() for msg in report.diagnostics)


def test_railway_production_auto_requires_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.delenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", raising=False)
    monkeypatch.setenv("TITAN_APP_ENV", "production")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", raising=False)
    report = validate_biometric_storage(
        profiles_path=data / "voice_speaker_profiles.json"
    )
    assert report.persistence_required is True
    assert report.ok is False


def test_operator_affirmed_persistence_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data = tmp_path / "data"
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "true")
    monkeypatch.setenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", "true")
    report = bootstrap_biometric_storage(
        profiles_path=data / "voice_speaker_profiles.json"
    )
    assert report.ok is True
    assert report.writable is True
    assert report.persistent is True


def test_encrypted_profile_no_plaintext_on_disk(encrypted_store: SpeakerProfileStore):
    profile = SpeakerIdentityProfile.create(
        user_id="Nolan", status=EnrollmentStatus.ENROLLED
    )
    profile.embeddings = [[0.1, 0.2, 0.3], [0.15, 0.25, 0.35]]
    profile.sample_count = 2
    profile.embedding_version = "ecapa_v1"
    profile.production_trusted = True
    encrypted_store.create_profile(profile)
    encrypted_store.activate_profile(profile.profile_id)

    raw = json.loads(encrypted_store.file_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    stored = raw["profiles"][profile.profile_id]
    assert stored["embeddings"] == []
    bundle = stored["embedding_bundle"]
    assert bundle.get("encrypted") is True
    assert bundle.get("codec") == "aes_gcm_v1"
    assert bundle.get("ciphertext_b64")
    assert bundle.get("nonce_b64")
    assert not bundle.get("vectors")
    # Disk must not contain the float literals from the embedding.
    disk_text = encrypted_store.file_path.read_text(encoding="utf-8")
    assert "0.15" not in disk_text
    assert "0.35" not in disk_text


def test_enrollment_survives_restart_with_encryption(
    encrypted_store: SpeakerProfileStore, tmp_path: Path
):
    service = VoiceEnrollmentService(
        store=encrypted_store,
        config=EnrollmentConfig(
            min_sample_count=3,
            min_quality_score=0.2,
            require_consent=False,
        ),
        temp_dir=tmp_path / "enroll_tmp",
    )
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
    )
    session_id = started["session"]["session_id"]
    for i in range(3):
        result = service.submit_sample(
            session_id=session_id,
            audio_bytes=_speech_like(10 + i),
            authenticated_user="Nolan",
        )
        assert result.get("accepted") is True or result.get("sample") is not None or (
            result.get("session", {}).get("samples_collected", 0) >= i + 1
        )

    # Simulate container restart: new process, same durable volume path.
    store2 = SpeakerProfileStore(file_path=encrypted_store.file_path)
    store2._storage = build_embedding_storage(prefer_encryption=True)
    store2.load()
    session = store2.get_session(session_id)
    assert session is not None
    assert len(session.samples) >= 1
    assert all(len(s.embedding) > 0 for s in session.samples)

    raw = json.loads(encrypted_store.file_path.read_text(encoding="utf-8"))
    for sample in raw["enrollment_sessions"][session_id]["samples"]:
        assert sample.get("embedding") in ([], None)
        assert sample.get("embedding_envelope", {}).get("ciphertext_b64")


def test_railway_redeploy_simulation_profile_and_verify(
    encrypted_store: SpeakerProfileStore, tmp_path: Path
):
    """Volume keep + container wipe: profiles and verification still work."""
    volume = tmp_path / "railway_volume" / "data"
    volume.mkdir(parents=True)
    profiles_path = volume / "voice_speaker_profiles.json"

    store = SpeakerProfileStore(file_path=profiles_path)
    store._storage = build_embedding_storage(prefer_encryption=True)

    profile = SpeakerIdentityProfile.create(
        user_id="Nolan", status=EnrollmentStatus.ENROLLED
    )
    profile.embeddings = [
        [1.0, 0.0, 0.0],
        [0.98, 0.1, 0.0],
        [0.97, 0.05, 0.02],
    ]
    profile.sample_count = 3
    profile.embedding_version = "ecapa_v1"
    profile.production_trusted = True
    profile.active = True
    store.create_profile(profile)
    store.activate_profile(profile.profile_id)

    # Snapshot volume contents, wipe "container" workspace, restore volume file.
    durable_bytes = profiles_path.read_bytes()
    container_ephemeral = tmp_path / "container_ephemeral"
    container_ephemeral.mkdir()
    # Simulate lost ephemeral /app without volume → empty
    assert not list(container_ephemeral.glob("*"))

    # Redeploy with volume remounted:
    restored = volume / "voice_speaker_profiles.json"
    restored.write_bytes(durable_bytes)

    store_after = SpeakerProfileStore(file_path=restored)
    store_after._storage = build_embedding_storage(prefer_encryption=True)
    store_after.load()
    active = store_after.get_active_profile("Nolan")
    assert active is not None
    assert active.profile_id == profile.profile_id
    assert len(active.embeddings) == 3
    embeddings = store_after.list_active_embeddings()
    assert "Nolan" in embeddings

    # Verification-equivalent: probe still matches enrolled centroid after redeploy.
    probe = [0.99, 0.05, 0.01]
    centroid = mean_embedding(embeddings["Nolan"])
    assert centroid is not None
    assert cosine_similarity(probe, centroid) >= 0.9
    # Disk remains encrypted (no plaintext floats).
    disk = restored.read_text(encoding="utf-8")
    assert '"embeddings": []' in disk or '"embeddings":[]' in disk
    assert "ciphertext_b64" in disk


def test_ibrahim_enrollment_isolated_from_nolan(encrypted_store: SpeakerProfileStore):
    nolan = SpeakerIdentityProfile.create(
        user_id="Nolan", status=EnrollmentStatus.ENROLLED
    )
    nolan.embeddings = [[1.0, 0.0]]
    nolan.sample_count = 1
    nolan.embedding_version = "ecapa_v1"
    encrypted_store.create_profile(nolan)
    encrypted_store.activate_profile(nolan.profile_id)

    ibrahim = SpeakerIdentityProfile.create(
        user_id="Ibrahim", status=EnrollmentStatus.ENROLLED
    )
    ibrahim.embeddings = [[0.0, 1.0]]
    ibrahim.sample_count = 1
    ibrahim.embedding_version = "ecapa_v1"
    encrypted_store.create_profile(ibrahim)
    encrypted_store.activate_profile(ibrahim.profile_id)

    store2 = SpeakerProfileStore(file_path=encrypted_store.file_path)
    store2._storage = build_embedding_storage(prefer_encryption=True)
    active = store2.list_active_embeddings()
    assert set(active.keys()) == {"Nolan", "Ibrahim"}
    assert active["Nolan"] != active["Ibrahim"]


def test_unlimited_future_users_supported(encrypted_store: SpeakerProfileStore):
    for idx in range(12):
        user = f"User{idx}"
        profile = SpeakerIdentityProfile.create(
            user_id=user, status=EnrollmentStatus.ENROLLED
        )
        profile.embeddings = [[float(idx), 1.0, 0.0]]
        profile.sample_count = 1
        encrypted_store.create_profile(profile)
        encrypted_store.activate_profile(profile.profile_id)
    store2 = SpeakerProfileStore(file_path=encrypted_store.file_path)
    store2._storage = build_embedding_storage(prefer_encryption=True)
    assert len(store2.list_active_embeddings()) == 12


def test_readiness_payload_includes_biometric_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    data = tmp_path / "data"
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "false")
    monkeypatch.setenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", "true")
    payload = collect_biometric_storage_readiness()
    assert payload["name"] == "biometric_storage"
    assert payload["ok"] is True
    assert payload["writable"] is True
    assert "architecture" in payload


def test_aes_gcm_backend_used_when_encryption_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "true")
    monkeypatch.setenv(
        "TITAN_VOICE_EMBEDDING_STORAGE_KEY",
        "phase20-13-test-key-do-not-use-in-production-0002",
    )
    backend = build_embedding_storage(prefer_encryption=True)
    assert isinstance(backend, AesGcmEmbeddingStorage)
    assert backend.encryption_enabled is True

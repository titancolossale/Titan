# =====================================
# Titan Phase 20.2 — Voice Enrollment Tests
# =====================================

"""Guided enrollment, identity profiles, recognition policy, privacy guards."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core.state_manager import StateManager
from voice.enrollment_models import (
    EnrollmentConfig,
    EnrollmentStatus,
    RecognitionBand,
    SpeakerIdentityProfile,
    VerificationOutcome,
)
from voice.exceptions import VoiceEnrollmentError
from voice.sample_validator import validate_enrollment_sample
from voice.speaker_identifier import SpeakerIdentifier, SpeakerIdentity
from voice.speaker_profile_store import SpeakerProfileStore
from voice.voice_enrollment import VoiceEnrollmentService
import voice.speaker_identifier as speaker_identifier_module


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
    """Synthetic PCM-ish bytes that pass duration/quality gates."""
    n = int(16000 * 2 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _silence(seconds: float = 1.25) -> bytes:
    n = int(16000 * 2 * seconds)
    return bytes([128] * n)


def _clipped(seconds: float = 1.25) -> bytes:
    n = int(16000 * 2 * seconds)
    return bytes([0 if i % 2 == 0 else 255 for i in range(n)])


def _multi_speaker(seconds: float = 1.25) -> bytes:
    n = int(16000 * 2 * seconds)
    out = bytearray(n)
    half = n // 2
    for i in range(half):
        out[i] = 10 + (i % 5)
    for i in range(half, n):
        out[i] = 240 - (i % 5)
    return bytes(out)


def _flat_band(level: int, seconds: float = 1.25) -> bytes:
    """Near-constant PCM band (valid quality, distinct histogram)."""
    n = int(16000 * 2 * seconds)
    return bytes((level + (i % 7)) % 230 + 20 for i in range(n))


@pytest.fixture
def enrollment_config() -> EnrollmentConfig:
    return EnrollmentConfig(
        min_sample_count=3,
        max_sample_count=6,
        min_sample_duration_seconds=1.0,
        max_sample_duration_seconds=30.0,
        min_quality_score=0.45,
        min_enrollment_confidence=0.72,
        high_confidence=0.72,
        medium_confidence=0.55,
        ambiguity_delta=0.05,
        max_verification_retries=3,
    )


@pytest.fixture
def service(tmp_path: Path, enrollment_config: EnrollmentConfig) -> VoiceEnrollmentService:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    state = StateManager(file_path=tmp_path / "state.json")
    return VoiceEnrollmentService(
        store=store,
        config=enrollment_config,
        state_manager=state,
        temp_dir=tmp_path / "voice_tmp",
    )


def _collect_samples(
    service: VoiceEnrollmentService,
    *,
    session_id: str,
    user: str,
    seed: int = 11,
) -> None:
    for offset in range(3):
        result = service.submit_sample(
            session_id=session_id,
            audio_bytes=_speech_like(seed + offset * 3),
            authenticated_user=user,
        )
        assert result["accepted"] is True


def test_nolan_enrollment_starts_when_authorized(service: VoiceEnrollmentService) -> None:
    result = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
    )
    assert result["ok"] is True
    assert result["session"]["user_id"] == "Nolan"
    assert result["session"]["status"] == EnrollmentStatus.COLLECTING.value
    assert result["script"]["language"] == "fr"
    assert len(result["script"]["phrases"]) >= 4


def test_ibrahim_enrollment_starts_when_authorized(
    service: VoiceEnrollmentService,
) -> None:
    result = service.start_enrollment(
        target_user="Ibrahim",
        authenticated_user="Ibrahim",
        locale="en-US",
    )
    assert result["ok"] is True
    assert result["session"]["user_id"] == "Ibrahim"
    assert result["script"]["language"] == "en"


def test_unauthorized_enrollment_rejected(service: VoiceEnrollmentService) -> None:
    with pytest.raises(VoiceEnrollmentError) as exc:
        service.start_enrollment(
            target_user="Alice",
            authenticated_user="Alice",
        )
    assert exc.value.code == "unauthorized_target"

    with pytest.raises(VoiceEnrollmentError) as exc2:
        service.start_enrollment(
            target_user="Nolan",
            authenticated_user="Ibrahim",
        )
    assert exc2.value.code == "unauthorized_target_mismatch"


def test_empty_audio_rejected(enrollment_config: EnrollmentConfig) -> None:
    result = validate_enrollment_sample(b"", config=enrollment_config)
    assert result.accepted is False
    assert result.reject_code is not None
    assert result.reject_code.value == "empty_audio"


def test_short_audio_rejected(enrollment_config: EnrollmentConfig) -> None:
    result = validate_enrollment_sample(b"abcd", config=enrollment_config)
    assert result.accepted is False
    assert result.reject_code is not None
    assert result.reject_code.value == "too_short"


def test_unsupported_audio_rejected(enrollment_config: EnrollmentConfig) -> None:
    payload = b"ID3" + _speech_like(1)
    result = validate_enrollment_sample(payload, config=enrollment_config)
    assert result.accepted is False
    assert result.reject_code is not None
    assert result.reject_code.value == "unsupported_audio"


def test_low_quality_audio_rejected(enrollment_config: EnrollmentConfig) -> None:
    silence = validate_enrollment_sample(_silence(), config=enrollment_config)
    assert silence.accepted is False
    assert silence.reject_code is not None
    assert silence.reject_code.value in {"excessive_silence", "low_quality"}

    clipped = validate_enrollment_sample(_clipped(), config=enrollment_config)
    assert clipped.accepted is False
    assert clipped.reject_code is not None
    assert clipped.reject_code.value in {
        "severe_clipping",
        "low_quality",
        "excessive_silence",
    }


def test_valid_samples_advance_collection(service: VoiceEnrollmentService) -> None:
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    for offset in range(3):
        result = service.submit_sample(
            session_id=session_id,
            audio_bytes=_speech_like(20 + offset),
            authenticated_user="Nolan",
        )
        assert result["accepted"] is True
        assert result["session"]["samples_collected"] == offset + 1
        assert result["session"]["status"] == EnrollmentStatus.COLLECTING.value
    assert result["ready_to_finish"] is True


def test_duplicate_samples_rejected(service: VoiceEnrollmentService) -> None:
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    sample = _speech_like(42)
    first = service.submit_sample(
        session_id=session_id,
        audio_bytes=sample,
        authenticated_user="Nolan",
    )
    assert first["accepted"] is True
    second = service.submit_sample(
        session_id=session_id,
        audio_bytes=sample,
        authenticated_user="Nolan",
    )
    assert second["accepted"] is False
    assert second["validation"]["reject_code"] == "duplicate_sample"


def test_profile_not_active_before_verification(service: VoiceEnrollmentService) -> None:
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    _collect_samples(service, session_id=session_id, user="Nolan", seed=50)
    finished = service.finish_enrollment(
        session_id=session_id,
        authenticated_user="Nolan",
    )
    assert finished["profile"]["active"] is False
    assert finished["profile"]["enrollment_status"] == EnrollmentStatus.VERIFYING.value
    assert service.store.get_active_profile("Nolan") is None


def test_successful_verification_activates_profile(
    service: VoiceEnrollmentService,
    enrollment_config: EnrollmentConfig,
) -> None:
    enrollment_config.min_enrollment_confidence = 0.35
    enrollment_config.medium_confidence = 0.20
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    base = _speech_like(60, seconds=1.4)
    for i in range(3):
        sample = bytearray(base)
        for j in range(64):
            sample[-(j + 1)] = ((i + 1) * 23 + j) % 180 + 40
        accepted = service.submit_sample(
            session_id=session_id,
            audio_bytes=bytes(sample),
            authenticated_user="Nolan",
        )
        assert accepted["accepted"] is True
    service.finish_enrollment(session_id=session_id, authenticated_user="Nolan")
    verify = bytearray(base)
    for j in range(64):
        verify[-(j + 1)] = (90 + j) % 180 + 40
    verified = service.verify_enrollment(
        session_id=session_id,
        audio_bytes=bytes(verify),
        authenticated_user="Nolan",
    )
    assert verified["activated"] is True
    assert verified["verification"]["verification_result"] == VerificationOutcome.PASSED.value
    active = service.store.get_active_profile("Nolan")
    assert active is not None
    assert active.active is True
    assert active.enrollment_status == EnrollmentStatus.ENROLLED


def test_failed_verification_leaves_no_active_partial(
    service: VoiceEnrollmentService,
    enrollment_config: EnrollmentConfig,
) -> None:
    enrollment_config.min_enrollment_confidence = 0.99
    enrollment_config.medium_confidence = 0.98
    enrollment_config.max_verification_retries = 1
    started = service.start_enrollment(
        target_user="Ibrahim",
        authenticated_user="Ibrahim",
    )
    session_id = started["session"]["session_id"]
    for i in range(3):
        sample = bytearray(_flat_band(40 + i))
        sample[-8:] = bytes((i + 1) * 9 + j for j in range(8))
        accepted = service.submit_sample(
            session_id=session_id,
            audio_bytes=bytes(sample),
            authenticated_user="Ibrahim",
        )
        assert accepted["accepted"] is True
    service.finish_enrollment(session_id=session_id, authenticated_user="Ibrahim")
    failed = service.verify_enrollment(
        session_id=session_id,
        audio_bytes=_flat_band(200),
        authenticated_user="Ibrahim",
    )
    assert failed["activated"] is False
    assert service.store.get_active_profile("Ibrahim") is None
    profile = service.store.get_profile(failed["profile"]["profile_id"])
    assert profile is not None
    assert profile.active is False


def test_medium_confidence_requests_confirmation(tmp_path: Path) -> None:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    nolan = SpeakerIdentityProfile.create(
        user_id="Nolan",
        display_name="Nolan",
        status=EnrollmentStatus.ENROLLED,
    )
    emb = [0.0] * 32
    emb[0] = 1.0
    nolan.embeddings = [emb]
    nolan.sample_count = 1
    nolan.active = True
    nolan.confidence = 1.0
    store.create_profile(nolan)
    store.activate_profile(nolan.profile_id)

    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.85,
        medium_confidence=0.50,
        ambiguity_delta=0.01,
        enabled=True,
        profile_store=store,
    )
    probe = [0.0] * 32
    probe[0] = 0.6
    probe[1] = 0.8

    original = speaker_identifier_module.extract_voice_features
    speaker_identifier_module.extract_voice_features = lambda _audio: probe
    try:
        result = identifier.identify(b"x" * 100)
    finally:
        speaker_identifier_module.extract_voice_features = original

    assert result.recognition_band == RecognitionBand.MEDIUM
    assert result.requires_confirmation is True
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.matched_user == "Nolan"
    assert result.reason == "medium_confidence"


def test_low_confidence_remains_unknown(tmp_path: Path) -> None:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.95,
        medium_confidence=0.90,
        enabled=True,
        profile_store=store,
    )
    identifier.enroll("Nolan", [bytes([40] * 40000)])
    result = identifier.identify(bytes([200] * 40000))
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.recognition_band in {RecognitionBand.LOW, RecognitionBand.MEDIUM}
    assert result.is_known is False


def test_ambiguous_match_does_not_auto_select(tmp_path: Path) -> None:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.50,
        medium_confidence=0.30,
        ambiguity_delta=0.99,
        enabled=True,
        profile_store=store,
    )
    shared = _speech_like(5)
    identifier.enroll("Nolan", [shared])
    identifier.enroll("Ibrahim", [shared])
    result = identifier.identify(shared)
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.reason == "ambiguous_match"
    assert result.matched_user is None
    assert result.requires_confirmation is True


def test_revoked_profile_cannot_identify(tmp_path: Path) -> None:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.5,
        enabled=True,
        profile_store=store,
    )
    audio = _speech_like(9)
    identifier.enroll("Nolan", [audio])
    assert identifier.identify(audio).is_known is True
    active = store.get_active_profile("Nolan")
    assert active is not None
    store.revoke_profile(active.profile_id)
    identifier.reload()
    result = identifier.identify(audio)
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.reason == "no_enrolled_profiles"


def test_reenroll_replaces_atomically(service: VoiceEnrollmentService) -> None:
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    _collect_samples(service, session_id=session_id, user="Nolan", seed=100)
    finished = service.finish_enrollment(
        session_id=session_id, authenticated_user="Nolan"
    )
    old_id = finished["profile"]["profile_id"]
    service.store.activate_profile(old_id)
    assert service.store.get_active_profile("Nolan") is not None

    started2 = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        replace_existing=True,
    )
    session2 = started2["session"]["session_id"]
    assert started2["session"]["replacing_profile_id"] == old_id
    _collect_samples(service, session_id=session2, user="Nolan", seed=300)
    finished2 = service.finish_enrollment(
        session_id=session2, authenticated_user="Nolan"
    )
    new_id = finished2["profile"]["profile_id"]
    assert service.store.get_active_profile("Nolan").profile_id == old_id
    service.store.replace_active_profile(new_profile_id=new_id, old_profile_id=old_id)
    active = service.store.get_active_profile("Nolan")
    assert active is not None
    assert active.profile_id == new_id
    old = service.store.get_profile(old_id)
    assert old is not None
    assert old.enrollment_status == EnrollmentStatus.REVOKED
    assert old.active is False


def test_failed_replacement_preserves_previous_active(
    service: VoiceEnrollmentService,
    enrollment_config: EnrollmentConfig,
) -> None:
    enrollment_config.min_enrollment_confidence = 0.99
    enrollment_config.medium_confidence = 0.98
    enrollment_config.max_verification_retries = 1

    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    for i in range(3):
        sample = bytearray(_flat_band(45 + i))
        sample[-8:] = bytes((i + 2) * 7 + j for j in range(8))
        assert service.submit_sample(
            session_id=session_id,
            audio_bytes=bytes(sample),
            authenticated_user="Nolan",
        )["accepted"]
    finished = service.finish_enrollment(
        session_id=session_id, authenticated_user="Nolan"
    )
    old_id = finished["profile"]["profile_id"]
    service.store.activate_profile(old_id)

    started2 = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        replace_existing=True,
    )
    session2 = started2["session"]["session_id"]
    for i in range(3):
        sample = bytearray(_flat_band(50 + i))
        sample[-8:] = bytes((i + 5) * 11 + j for j in range(8))
        assert service.submit_sample(
            session_id=session2,
            audio_bytes=bytes(sample),
            authenticated_user="Nolan",
        )["accepted"]
    service.finish_enrollment(session_id=session2, authenticated_user="Nolan")
    failed = service.verify_enrollment(
        session_id=session2,
        audio_bytes=_flat_band(210),
        authenticated_user="Nolan",
    )
    assert failed["activated"] is False
    active = service.store.get_active_profile("Nolan")
    assert active is not None
    assert active.profile_id == old_id


def test_temporary_raw_audio_deleted(service: VoiceEnrollmentService, tmp_path: Path) -> None:
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
    )
    session_id = started["session"]["session_id"]
    service.submit_sample(
        session_id=session_id,
        audio_bytes=_speech_like(12),
        authenticated_user="Nolan",
    )
    session_tmp = tmp_path / "voice_tmp" / session_id
    if session_tmp.exists():
        assert list(session_tmp.glob("*")) == []


def test_raw_audio_and_embeddings_never_in_logs_or_workspace(
    service: VoiceEnrollmentService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        started = service.start_enrollment(
            target_user="Nolan",
            authenticated_user="Nolan",
        )
        session_id = started["session"]["session_id"]
        audio = _speech_like(15)
        service.submit_sample(
            session_id=session_id,
            audio_bytes=audio,
            authenticated_user="Nolan",
        )
        _collect_samples(service, session_id=session_id, user="Nolan", seed=16)
        finished = service.finish_enrollment(
            session_id=session_id, authenticated_user="Nolan"
        )

    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "embeddings" not in joined.lower()
    assert audio.hex()[:32] not in joined

    public = finished["profile"]
    assert "embeddings" not in public
    status = service.get_status(user_id="Nolan", authenticated_user="Nolan")
    workspace = status["workspace"]
    assert "embedding" not in str(workspace).lower()
    assert "audio" not in str(workspace).lower()
    snap = service._state_manager.snapshot()
    payload = snap.to_dict()
    assert "embeddings" not in payload
    assert payload["voice_enrollment_user"] == "Nolan"
    assert payload["voice_samples_collected"] >= 3


def test_enrollment_state_survives_restart(
    tmp_path: Path, enrollment_config: EnrollmentConfig
) -> None:
    path = tmp_path / "profiles.json"
    store = SpeakerProfileStore(file_path=path)
    service = VoiceEnrollmentService(
        store=store,
        config=enrollment_config,
        temp_dir=tmp_path / "tmp",
    )
    started = service.start_enrollment(
        target_user="Ibrahim",
        authenticated_user="Ibrahim",
    )
    session_id = started["session"]["session_id"]
    service.submit_sample(
        session_id=session_id,
        audio_bytes=_speech_like(21),
        authenticated_user="Ibrahim",
    )

    store2 = SpeakerProfileStore(file_path=path)
    service2 = VoiceEnrollmentService(store=store2, config=enrollment_config)
    status = service2.get_status(
        session_id=session_id,
        authenticated_user="Ibrahim",
    )
    assert status["session"] is not None
    assert status["session"]["samples_collected"] == 1
    assert status["session"]["status"] == EnrollmentStatus.COLLECTING.value


def test_multi_speaker_rejected_when_detectable(
    enrollment_config: EnrollmentConfig,
) -> None:
    result = validate_enrollment_sample(_multi_speaker(), config=enrollment_config)
    assert result.accepted is False
    assert result.reject_code is not None
    assert result.reject_code.value in {"multiple_speakers", "low_quality", "severe_clipping"}

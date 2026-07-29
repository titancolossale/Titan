# =====================================
# Titan Phase 20.10A — Production Voice Enrollment System Tests
# =====================================

"""Production enrollment workflow, quality, verification, audit, diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.titan_service import reset_titan
from core.state_manager import StateManager
from voice.embedding_provider import reset_embedding_registry_for_tests
from voice.enrollment_audit import make_audit_event
from voice.enrollment_diagnostics import collect_enrollment_diagnostics
from voice.enrollment_models import EnrollmentConfig, EnrollmentStatus, VerificationOutcome
from voice.enrollment_quality import analyze_production_quality
from voice.enrollment_verification import (
    EnrollmentVerificationPipeline,
    VerificationThresholds,
)
from voice.enrollment_workflow import (
    ALLOWED_TRANSITIONS,
    EnrollmentWorkflowController,
    ProductionEnrollmentState,
    legacy_to_production,
    production_to_legacy,
)
from voice.exceptions import VoiceEnrollmentError
from voice.sample_validator import validate_enrollment_sample
from voice.speaker_profile_store import SpeakerProfileStore
from voice.voice_enrollment import VoiceEnrollmentService


def _speech_like(seed: int, seconds: float = 2.5) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _enrollment_service(tmp_path: Path, **config_kwargs: object) -> VoiceEnrollmentService:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    defaults = {
        "min_sample_count": 3,
        "min_quality_score": 0.2,
        "require_consent": True,
        "min_enrollment_confidence": 0.5,
        "medium_confidence": 0.35,
    }
    defaults.update(config_kwargs)
    return VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(**defaults),  # type: ignore[arg-type]
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "enroll_tmp",
    )


@pytest.fixture(autouse=True)
def _reset_embeddings():
    reset_embedding_registry_for_tests()
    yield
    reset_embedding_registry_for_tests()


def test_production_states_complete():
    expected = {
        "WAITING_CONSENT",
        "CONSENT_GRANTED",
        "READY_TO_RECORD",
        "RECORDING",
        "VERIFYING",
        "SUCCESS",
        "FAILED",
        "CANCELLED",
        "RECOVERY",
    }
    assert {s.value for s in ProductionEnrollmentState} == expected


def test_allowed_transitions_cover_happy_path():
    ctrl = EnrollmentWorkflowController()
    assert ctrl.can_transition(
        ProductionEnrollmentState.WAITING_CONSENT,
        ProductionEnrollmentState.CONSENT_GRANTED,
    )
    assert ctrl.can_transition(
        ProductionEnrollmentState.CONSENT_GRANTED,
        ProductionEnrollmentState.READY_TO_RECORD,
    )
    assert ctrl.can_transition(
        ProductionEnrollmentState.READY_TO_RECORD,
        ProductionEnrollmentState.RECORDING,
    )
    assert ctrl.can_transition(
        ProductionEnrollmentState.RECORDING,
        ProductionEnrollmentState.VERIFYING,
    )
    assert ctrl.can_transition(
        ProductionEnrollmentState.VERIFYING,
        ProductionEnrollmentState.SUCCESS,
    )


def test_invalid_transition_raises():
    ctrl = EnrollmentWorkflowController()
    with pytest.raises(VoiceEnrollmentError) as exc:
        ctrl.transition(
            ProductionEnrollmentState.WAITING_CONSENT,
            ProductionEnrollmentState.SUCCESS,
            reason="illegal",
        )
    assert exc.value.code == "invalid_workflow_transition"


def test_legacy_production_mapping_roundtrip():
    assert (
        legacy_to_production(EnrollmentStatus.AWAITING_CONSENT)
        == ProductionEnrollmentState.WAITING_CONSENT
    )
    assert (
        production_to_legacy(ProductionEnrollmentState.SUCCESS)
        == EnrollmentStatus.ENROLLED
    )


def test_all_states_have_transition_rules():
    for state in ProductionEnrollmentState:
        assert state in ALLOWED_TRANSITIONS


def test_full_workflow_waiting_consent_to_verify(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    started = svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        locale="fr-FR",
    )
    assert started["session"]["status"] == EnrollmentStatus.AWAITING_CONSENT.value
    assert started["session"]["workflow_state"] == "WAITING_CONSENT"
    sid = started["session"]["session_id"]

    granted = svc.grant_consent(
        session_id=sid, authenticated_user="Nolan", accepted=True
    )
    assert granted["ok"] is True
    assert granted["session"]["workflow_state"] == "READY_TO_RECORD"

    for i in range(3):
        accepted = svc.submit_sample(
            session_id=sid,
            audio_bytes=_speech_like(10 + i),
            authenticated_user="Nolan",
        )
        assert accepted["accepted"] is True
        assert "production_metrics" in accepted["validation"]

    finished = svc.finish_enrollment(session_id=sid, authenticated_user="Nolan")
    assert finished["ok"] is True
    assert finished["session"]["workflow_state"] == "VERIFYING"
    assert finished["profile"]["profile_version"] >= 1
    assert "embeddings" not in finished["profile"]

    verify = svc.verify_enrollment(
        session_id=sid,
        audio_bytes=_speech_like(10),
        authenticated_user="Nolan",
    )
    assert "verification" in verify
    assert verify["session"]["workflow_state"] in {"SUCCESS", "VERIFYING", "FAILED"}
    assert "embeddings" not in (verify.get("profile") or {})


def test_consent_decline_cancels(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    started = svc.start_enrollment(
        target_user="Ibrahim", authenticated_user="Ibrahim"
    )
    sid = started["session"]["session_id"]
    declined = svc.grant_consent(
        session_id=sid, authenticated_user="Ibrahim", accepted=False
    )
    assert declined["ok"] is False
    assert declined["session"]["workflow_state"] == "CANCELLED"


def test_safe_cancellation(tmp_path: Path):
    svc = _enrollment_service(tmp_path, require_consent=False)
    started = svc.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    sid = started["session"]["session_id"]
    cancelled = svc.cancel_enrollment(session_id=sid, authenticated_user="Nolan")
    assert cancelled["cancelled"] is True
    assert cancelled["session"]["workflow_state"] == "CANCELLED"


def test_multiple_attempts_and_resume(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    first = svc.start_enrollment(target_user="Nolan", authenticated_user="Nolan")
    sid1 = first["session"]["session_id"]
    token = first["session"]["recovery_token"]

    recovered = svc.recover_enrollment(
        session_id=sid1,
        recovery_token=token,
        authenticated_user="Nolan",
    )
    assert recovered["recovered"] is True

    second = svc.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", session_label="attempt-2"
    )
    assert second["session"]["attempt_number"] >= 2
    prior = svc.store.get_session(sid1)
    assert prior is not None
    assert prior.status == EnrollmentStatus.CANCELLED


def test_replacement_enrollment_versions_profile(tmp_path: Path):
    svc = _enrollment_service(tmp_path, require_consent=False)
    from voice.enrollment_models import SpeakerIdentityProfile

    store = svc.store
    v1 = SpeakerIdentityProfile.create(
        user_id="Nolan",
        status=EnrollmentStatus.ENROLLED,
        profile_version=1,
    )
    v1.active = True
    v1.embeddings = [[0.1] * 64]
    store.create_profile(v1)
    store.activate_profile(v1.profile_id)

    started = svc.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        replace_existing=True,
        consent_accepted=True,
    )
    sid = started["session"]["session_id"]
    for i in range(3):
        svc.submit_sample(
            session_id=sid,
            audio_bytes=_speech_like(20 + i),
            authenticated_user="Nolan",
        )
    finished = svc.finish_enrollment(session_id=sid, authenticated_user="Nolan")
    assert finished["ok"] is True
    assert finished["profile"]["profile_version"] == 2
    assert finished["replacement_plan"]["revoke_old"] is True


def test_duplicate_sample_rejected(tmp_path: Path):
    svc = _enrollment_service(tmp_path, require_consent=False)
    started = svc.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    sid = started["session"]["session_id"]
    audio = _speech_like(99)
    first = svc.submit_sample(
        session_id=sid, audio_bytes=audio, authenticated_user="Nolan"
    )
    assert first["accepted"] is True
    dup = svc.submit_sample(
        session_id=sid, audio_bytes=audio, authenticated_user="Nolan"
    )
    assert dup["accepted"] is False
    assert dup["validation"]["reject_code"] == "duplicate_sample"


def test_audit_history_recorded(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    started = svc.start_enrollment(target_user="Nolan", authenticated_user="Nolan")
    audit = svc.store.list_audit_history(user_id="Nolan")
    assert any(e["event_type"] == "enrollment_started" for e in audit)
    sid = started["session"]["session_id"]
    svc.grant_consent(session_id=sid, authenticated_user="Nolan", accepted=True)
    audit2 = svc.store.list_audit_history(user_id="Nolan", session_id=sid)
    assert any(e["event_type"] == "consent_granted" for e in audit2)
    for event in audit2:
        assert "embedding" not in event.get("metadata", {})
        assert "audio" not in event.get("metadata", {})


def test_revocation(tmp_path: Path):
    svc = _enrollment_service(tmp_path, require_consent=False)
    from voice.enrollment_models import SpeakerIdentityProfile

    profile = SpeakerIdentityProfile.create(
        user_id="Ibrahim", status=EnrollmentStatus.ENROLLED
    )
    profile.active = True
    profile.embeddings = [[0.2] * 64]
    svc.store.create_profile(profile)
    svc.store.activate_profile(profile.profile_id)
    revoked = svc.revoke_profile(user_id="Ibrahim", authenticated_user="Ibrahim")
    assert revoked["ok"] is True
    assert revoked["profile"]["enrollment_status"] == EnrollmentStatus.REVOKED.value
    assert "embeddings" not in revoked["profile"]
    assert svc.store.get_active_profile("Ibrahim") is None


def test_production_quality_metrics_keys():
    audio = _speech_like(5)
    metrics = analyze_production_quality(
        audio, config=EnrollmentConfig(min_quality_score=0.1)
    )
    payload = metrics.to_dict()
    for key in (
        "signal_level",
        "background_noise",
        "speech_duration_seconds",
        "language_independence",
        "duplicate_recording",
        "clipping_ratio",
        "microphone_quality",
        "overall_score",
        "passed",
    ):
        assert key in payload


def test_validate_sample_includes_production_metrics():
    result = validate_enrollment_sample(
        _speech_like(7),
        config=EnrollmentConfig(min_quality_score=0.1),
    )
    assert result.production_metrics is not None
    assert "signal_level" in result.production_metrics


def test_empty_audio_fails_quality():
    metrics = analyze_production_quality(b"")
    assert metrics.passed is False
    assert "empty_audio" in metrics.reject_reasons


def test_clipping_rejected():
    clipped = bytes([0 if i % 2 == 0 else 255 for i in range(16000 * 2)])
    result = validate_enrollment_sample(
        clipped, config=EnrollmentConfig(min_quality_score=0.1)
    )
    assert result.accepted is False


def test_verification_pipeline_pass_and_retry():
    pipeline = EnrollmentVerificationPipeline(
        VerificationThresholds(pass_threshold=0.9, medium=0.5, max_retries=3)
    )
    # Provider cosine is a dot product over L2-normalized vectors.
    emb = [1.0] + [0.0] * 63
    passed = pipeline.score_probe(
        probe_embedding=emb,
        profile_embeddings=[emb],
        expected_user_id="Nolan",
        profile_embedding_version="histogram_v1",
        retries_used=0,
    )
    assert passed.verification.outcome == VerificationOutcome.PASSED
    assert passed.retry_allowed is False

    weak = [0.0] * 64
    weak[1] = 1.0
    failed = pipeline.score_probe(
        probe_embedding=weak,
        profile_embeddings=[emb],
        expected_user_id="Nolan",
        profile_embedding_version="histogram_v1",
        retries_used=0,
    )
    assert failed.verification.outcome != VerificationOutcome.PASSED
    assert failed.retry_allowed is True


def test_verification_thresholds_from_config():
    cfg = EnrollmentConfig(min_enrollment_confidence=0.8, max_verification_retries=2)
    thresholds = VerificationThresholds.from_config(cfg)
    assert thresholds.pass_threshold == 0.8
    assert thresholds.max_retries == 2


def test_public_session_hides_embeddings(tmp_path: Path):
    svc = _enrollment_service(tmp_path, require_consent=False)
    started = svc.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    sid = started["session"]["session_id"]
    svc.submit_sample(
        session_id=sid,
        audio_bytes=_speech_like(3),
        authenticated_user="Nolan",
    )
    status = svc.get_status(user_id="Nolan", session_id=sid, authenticated_user="Nolan")
    for sample in status["session"]["samples"]:
        assert "embedding" not in sample
        assert "feature_fingerprint" not in sample


def test_audit_event_strips_unsafe_metadata():
    event = make_audit_event(
        event_type="test",
        user_id="Nolan",
        metadata={"embedding": [1, 2], "ok": True, "audio_bytes": b"x"},
    )
    assert "embedding" not in event.metadata
    assert "audio_bytes" not in event.metadata
    assert event.metadata["ok"] is True


def test_diagnostics_track_workflow_and_failures(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    started = svc.start_enrollment(target_user="Nolan", authenticated_user="Nolan")
    sid = started["session"]["session_id"]
    svc.grant_consent(session_id=sid, authenticated_user="Nolan", accepted=False)
    snap = collect_enrollment_diagnostics(store=svc.store, user_id="Nolan")
    assert snap["ok"] is True
    assert "workflow" in snap
    assert "state_counts" in snap["workflow"]
    assert "audit_history" in snap
    assert "verification_confidence" in snap


def test_api_workflow_and_audit_endpoints(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_SESSION_AUTH_ENABLED", "false")
    reset_titan()
    app = create_app()
    from api import voice_enrollment_routes as routes

    routes._enrollment_service = None  # noqa: SLF001
    monkeypatch.setattr(
        "config.settings.TITAN_VOICE_SPEAKER_PROFILES_PATH",
        tmp_path / "api_profiles.json",
    )
    monkeypatch.setattr(
        "config.settings.TITAN_VOICE_ENROLLMENT_TEMP_DIR",
        tmp_path / "api_enroll_tmp",
    )
    monkeypatch.setattr(
        "config.settings.TITAN_STATE_PATH",
        tmp_path / "api_state.json",
    )
    monkeypatch.setattr(
        "config.settings.TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT",
        True,
    )

    client = TestClient(app)
    start = client.post(
        "/voice/enrollment/start",
        json={"user": "Nolan", "locale": "fr-FR", "consent_accepted": False},
    )
    assert start.status_code == 200
    body = start.json()
    assert body["session"]["workflow_state"] == "WAITING_CONSENT"
    sid = body["session"]["session_id"]

    workflow = client.get(f"/voice/enrollment/workflow?session_id={sid}")
    assert workflow.status_code == 200
    assert workflow.json()["workflow"]["workflow_state"] == "WAITING_CONSENT"

    audit = client.get("/voice/enrollment/audit")
    assert audit.status_code == 200
    assert audit.json()["ok"] is True

    diag = client.get("/voice/enrollment/diagnostics")
    assert diag.status_code == 200
    assert "workflow" in diag.json()

    routes._enrollment_service = None  # noqa: SLF001
    reset_titan()


def test_status_includes_workflow_and_thresholds(tmp_path: Path):
    svc = _enrollment_service(tmp_path)
    started = svc.start_enrollment(target_user="Nolan", authenticated_user="Nolan")
    status = svc.get_status(
        user_id="Nolan",
        session_id=started["session"]["session_id"],
        authenticated_user="Nolan",
    )
    assert status["workflow"] is not None
    assert status["verification_thresholds"]["pass_threshold"] > 0
    assert isinstance(status["audit_history"], list)

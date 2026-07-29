# =====================================
# Titan Phase 20.9 — Real Speaker Enrollment & Live Provider Soak Tests
# =====================================

"""Real enrollment pipeline, embedding stubs, soak, diagnostics, performance."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agents.agent_manager import AgentManager
from api.app import create_app
from api.titan_service import reset_titan, set_titan
from api.voice_session_routes import reset_live_orchestrator_for_tests
from brain.brain import Brain
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from core.titan import Titan
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager
from voice.diagnostics import VOICE_DIAGNOSTIC_EVENTS, VOICE_STREAM_EVENTS
from voice.embedding_provider import (
    ECAPA_VERSION,
    EcapaEmbeddingProvider,
    HistogramEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    ResemblyzerEmbeddingProvider,
    extract_embeddings_batch,
    get_embedding_provider,
    get_embedding_registry,
    reset_embedding_registry_for_tests,
    set_embedding_provider,
)
from voice.enrollment_consent import (
    CONSENT_VERSION,
    get_consent_prompt,
    list_consent_prompts,
    record_consent,
)
from voice.enrollment_diagnostics import collect_enrollment_diagnostics
from voice.enrollment_models import EnrollmentConfig, EnrollmentStatus
from voice.enrollment_quality import (
    detect_same_user_near_duplicate,
    score_session_quality,
)
from voice.enrollment_scripts import (
    BILINGUAL_ENROLLMENT_SCRIPT,
    SPANISH_ENROLLMENT_SCRIPT,
    get_enrollment_script,
    list_enrollment_scripts,
)
from voice.exceptions import VoiceConfigurationError, VoiceEnrollmentError
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.models import VoiceConfig
from voice.production_soak import (
    DEFAULT_SOAK_SCENARIOS,
    SoakScenarioId,
    VoiceProductionSoakRunner,
)
from voice.speaker_identifier import SpeakerIdentifier, extract_voice_features
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.voice_enrollment import VoiceEnrollmentService
from voice.voice_session import VoiceSessionStore


def _speech_like(seed: int, seconds: float = 2.5) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse vocale de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )


def _orchestrator(tmp_path: Path) -> LiveVoiceSessionOrchestrator:
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Bonjour, je suis Titan.")
    )
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "legacy_profiles.json",
        profile_store=store,
        enabled=True,
    )
    stt = SpeechToTextRegistry()
    stt.register(MockSpeechToTextProvider(default_text="bonjour titan"))
    return LiveVoiceSessionOrchestrator(
        brain,
        speaker_identifier=identifier,
        session_store=VoiceSessionStore(file_path=tmp_path / "sessions.json"),
        state_manager=brain.state_manager,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        stt_registry=stt,
        temp_dir=tmp_path / "voice_tmp",
        idle_timeout_seconds=30.0,
        conversation_timeout_seconds=600.0,
    )


def _enrollment_service(tmp_path: Path, **config_kwargs: object) -> VoiceEnrollmentService:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    defaults = {
        "min_sample_count": 3,
        "min_quality_score": 0.2,
        "require_consent": True,
    }
    defaults.update(config_kwargs)
    return VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(**defaults),  # type: ignore[arg-type]
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "enroll_tmp",
    )


# ---------------------------------------------------------------------------
# Consent + multi-language
# ---------------------------------------------------------------------------


def test_consent_prompts_multi_language():
    fr = get_consent_prompt("fr-FR")
    en = get_consent_prompt("en-US")
    es = get_consent_prompt("es-ES")
    assert fr.language == "fr"
    assert en.language == "en"
    assert es.language == "es"
    assert fr.version == CONSENT_VERSION
    prompts = list_consent_prompts()
    assert len(prompts) == 3
    record = record_consent(accepted=True, locale="fr-FR")
    assert record.given is True
    assert record.recorded_at is not None


def test_multi_language_enrollment_scripts():
    scripts = list_enrollment_scripts()
    ids = {s["script_id"] for s in scripts}
    assert "fr_default" in ids
    assert "en_default" in ids
    assert "es_default" in ids
    assert "bilingual_fr_en" in ids
    assert get_enrollment_script("es").script_id == SPANISH_ENROLLMENT_SCRIPT.script_id
    assert get_enrollment_script("bilingual").script_id == (
        BILINGUAL_ENROLLMENT_SCRIPT.script_id
    )


def test_enrollment_requires_consent_before_samples(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=True)
    started = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=False,
    )
    assert started["session"]["status"] == EnrollmentStatus.AWAITING_CONSENT.value
    sid = started["session"]["session_id"]
    with pytest.raises(VoiceEnrollmentError) as exc:
        service.submit_sample(
            session_id=sid,
            audio_bytes=_speech_like(1),
            authenticated_user="Nolan",
        )
    assert exc.value.code == "consent_required"
    granted = service.grant_consent(
        session_id=sid, authenticated_user="Nolan", accepted=True
    )
    assert granted["ok"] is True
    assert granted["session"]["status"] == EnrollmentStatus.COLLECTING.value
    accepted = service.submit_sample(
        session_id=sid,
        audio_bytes=_speech_like(2, 2.5),
        authenticated_user="Nolan",
    )
    assert accepted["ok"] is True, accepted
    assert "session_quality" in accepted


def test_consent_declined_cancels_session(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=True)
    started = service.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan"
    )
    sid = started["session"]["session_id"]
    declined = service.grant_consent(
        session_id=sid, authenticated_user="Nolan", accepted=False
    )
    assert declined["ok"] is False
    assert declined["session"]["status"] == EnrollmentStatus.CANCELLED.value


def test_enrollment_cancellation_status(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=False)
    started = service.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    sid = started["session"]["session_id"]
    cancelled = service.cancel_enrollment(session_id=sid, authenticated_user="Nolan")
    assert cancelled["cancelled"] is True
    assert cancelled["session"]["status"] == EnrollmentStatus.CANCELLED.value


def test_enrollment_recovery(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=True)
    started = service.start_enrollment(
        target_user="Ibrahim",
        authenticated_user="Ibrahim",
        consent_accepted=True,
        locale="en-US",
    )
    sid = started["session"]["session_id"]
    token = started["session"]["recovery_token"]
    submitted = service.submit_sample(
        session_id=sid,
        audio_bytes=_speech_like(10, 2.5),
        authenticated_user="Ibrahim",
    )
    assert submitted["ok"] is True, submitted
    recovered = service.recover_enrollment(
        session_id=sid,
        recovery_token=token,
        authenticated_user="Ibrahim",
    )
    assert recovered["recovered"] is True
    assert recovered["session"]["samples_collected"] == 1
    with pytest.raises(VoiceEnrollmentError) as exc:
        service.recover_enrollment(
            session_id=sid,
            recovery_token="wrong-token",
            authenticated_user="Ibrahim",
        )
    assert exc.value.code == "invalid_recovery_token"


def test_profile_replace_and_same_user_near_duplicate(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=False, min_sample_count=3)
    samples = [_speech_like(50 + i, 2.0) for i in range(3)]
    started = service.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    sid = started["session"]["session_id"]
    for audio in samples:
        assert service.submit_sample(
            session_id=sid, audio_bytes=audio, authenticated_user="Nolan"
        )["ok"]
    finished = service.finish_enrollment(session_id=sid, authenticated_user="Nolan")
    assert finished["ok"] is True
    # Activate via verify with same audio family may hit duplicate fingerprint —
    # force-activate for replace path test.
    pending_id = finished["profile"]["profile_id"]
    service.store.activate_profile(pending_id)

    # Re-enroll with replace.
    started2 = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
        replace_existing=True,
        session_label="replace_pass",
    )
    assert started2["replacement_plan"]["action"] == "atomic_replace"
    sid2 = started2["session"]["session_id"]
    for audio in samples:
        assert service.submit_sample(
            session_id=sid2, audio_bytes=audio, authenticated_user="Nolan"
        )["ok"]
    finished2 = service.finish_enrollment(session_id=sid2, authenticated_user="Nolan")
    assert finished2["ok"] is True
    assert finished2["same_user_near_duplicate"]["is_duplicate"] is True
    assert finished2["replacement_plan"]["revoke_old"] is True


# ---------------------------------------------------------------------------
# Embedding preparation
# ---------------------------------------------------------------------------


def test_embedding_registry_future_providers_unavailable():
    reset_embedding_registry_for_tests()
    set_embedding_provider(None)
    registry = get_embedding_registry()
    providers = {p["provider_id"]: p for p in registry.list_providers()}
    assert providers["histogram"]["available"] is True
    # ECAPA becomes available once torch+speechbrain are installed (Phase 20.12B).
    ecapa = EcapaEmbeddingProvider()
    assert providers["ecapa"]["available"] is ecapa.is_available
    assert providers["resemblyzer"]["available"] is ResemblyzerEmbeddingProvider().is_available
    assert providers["openai_compat"]["available"] is False
    assert registry.active.embedding_version == "histogram_v1"
    if ecapa.is_available:
        registry.set_active("ecapa")
        assert registry.active.provider_id == "ecapa"
        registry.set_active("histogram")
    else:
        with pytest.raises(VoiceConfigurationError):
            ecapa.extract(b"x")
        with pytest.raises(VoiceConfigurationError):
            registry.set_active("ecapa")
    assert OpenAICompatibleEmbeddingProvider().embedding_version.startswith("openai")
    assert ResemblyzerEmbeddingProvider().embedding_version.startswith("resemblyzer")
    assert ECAPA_VERSION == "ecapa_v1"


def test_batch_embedding_extract_performance_path():
    set_embedding_provider(HistogramEmbeddingProvider())
    samples = [_speech_like(i, 0.5) for i in range(5)]
    batch = extract_embeddings_batch(samples)
    assert len(batch) == 5
    assert all(len(row) == 32 for row in batch)


def test_session_quality_scoring():
    embeddings = [extract_voice_features(_speech_like(i)) for i in range(3)]
    report = score_session_quality(
        sample_scores=[0.8, 0.7, 0.9],
        embeddings=embeddings,
        required_samples=3,
    )
    assert report.ready_to_finish is True
    assert 0.0 < report.aggregate_score <= 1.0


# ---------------------------------------------------------------------------
# Live provider soak
# ---------------------------------------------------------------------------


def test_phase20_9_soak_scenarios_present():
    ids = {s.scenario_id for s in DEFAULT_SOAK_SCENARIOS}
    assert SoakScenarioId.VOICE_VERIFICATION in ids
    assert SoakScenarioId.ENROLLMENT_CONSENT_RECOVERY in ids
    assert SoakScenarioId.LIVE_PROVIDER_RECOVERY in ids
    assert SoakScenarioId.MULTIPLE_CONVERSATIONS in ids
    assert SoakScenarioId.PROVIDER_FALLBACK in ids
    assert SoakScenarioId.RAILWAY_DEPLOYMENT in ids


def test_phase20_9_soak_runner(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    runner = VoiceProductionSoakRunner(orch, speech_factory=_speech_like)
    report = runner.run(
        scenarios=tuple(
            s
            for s in DEFAULT_SOAK_SCENARIOS
            if s.scenario_id
            in {
                SoakScenarioId.VOICE_VERIFICATION,
                SoakScenarioId.ENROLLMENT_CONSENT_RECOVERY,
                SoakScenarioId.LIVE_PROVIDER_RECOVERY,
                SoakScenarioId.MULTIPLE_CONVERSATIONS,
                SoakScenarioId.PROVIDER_RECONNECT,
                SoakScenarioId.NETWORK_INTERRUPTION,
                SoakScenarioId.PROVIDER_FALLBACK,
                SoakScenarioId.RAILWAY_DEPLOYMENT,
                SoakScenarioId.SPEAKER_SWITCHING,
            }
        )
    )
    assert report.ok, report.to_dict()
    assert report.to_dict()["passed"] == 9


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_enrollment_diagnostics_snapshot(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=False)
    service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        consent_accepted=True,
        session_label="diag",
    )
    snap = collect_enrollment_diagnostics(store=service.store, user_id="Nolan")
    assert snap["ok"] is True
    assert "provider_status" in snap
    assert "embedding_quality" in snap
    assert "speaker_confidence" in snap
    assert "verification_confidence" in snap
    assert "session_history" in snap
    assert "latency" in snap
    assert "provider_health" in snap
    assert snap["provider_status"]["embedding"]["providers"]


def test_phase20_9_diagnostic_events_registered():
    for event in (
        "VOICE_ENROLLMENT_CONSENT_GRANTED",
        "VOICE_ENROLLMENT_RECOVERED",
        "ENROLLMENT_DIAGNOSTICS_SNAPSHOT",
        "LIVE_PROVIDER_RECOVERY",
    ):
        assert event in VOICE_DIAGNOSTIC_EVENTS
    assert "ENROLLMENT_DIAGNOSTICS_SNAPSHOT" in VOICE_STREAM_EVENTS


def test_enrollment_api_consent_recover_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "false")
    monkeypatch.setenv("TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT", "true")
    reset_titan()
    reset_live_orchestrator_for_tests()
    # Reset process-scoped enrollment service.
    import api.voice_enrollment_routes as enroll_routes

    enroll_routes._enrollment_service = None  # noqa: SLF001
    brain = _build_brain(tmp_path)
    titan = Titan.__new__(Titan)
    titan.brain = brain
    titan.state_manager = brain.state_manager
    titan.mission_manager = brain.mission_manager
    set_titan(titan)
    # Point store at tmp via monkeypatched service.
    service = _enrollment_service(tmp_path, require_consent=True)
    enroll_routes._enrollment_service = service
    app = create_app()
    client = TestClient(app)

    scripts = client.get("/voice/enrollment/scripts")
    assert scripts.status_code == 200
    assert len(scripts.json()["scripts"]) >= 4

    started = client.post(
        "/voice/enrollment/start",
        json={"user": "Nolan", "locale": "fr-FR", "consent_accepted": False},
    )
    assert started.status_code == 200
    body = started.json()
    sid = body["session"]["session_id"]
    token = body["session"]["recovery_token"]
    assert body["session"]["status"] == EnrollmentStatus.AWAITING_CONSENT.value

    consent = client.post(
        "/voice/enrollment/consent",
        json={"session_id": sid, "accepted": True},
    )
    assert consent.status_code == 200
    assert consent.json()["accepted"] is True

    recovered = client.post(
        "/voice/enrollment/recover",
        json={"session_id": sid, "recovery_token": token},
    )
    assert recovered.status_code == 200
    assert recovered.json()["recovered"] is True

    diag = client.get("/voice/enrollment/diagnostics")
    assert diag.status_code == 200
    assert diag.json()["ok"] is True


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_enrollment_processing_records_latency(tmp_path: Path):
    service = _enrollment_service(tmp_path, require_consent=False)
    started = service.start_enrollment(
        target_user="Nolan", authenticated_user="Nolan", consent_accepted=True
    )
    assert started["session"]["processing_latency_ms"] >= 0.0
    sid = started["session"]["session_id"]
    accepted = service.submit_sample(
        session_id=sid,
        audio_bytes=_speech_like(99, 2.5),
        authenticated_user="Nolan",
    )
    assert accepted["session"]["processing_latency_ms"] >= 0.0


def test_detect_same_user_near_duplicate_helper():
    from voice.enrollment_models import SpeakerIdentityProfile

    emb = extract_voice_features(_speech_like(7))
    profile = SpeakerIdentityProfile.create(
        user_id="Nolan", status=EnrollmentStatus.ENROLLED
    )
    profile.embeddings = [emb, emb]
    profile.active = True
    result = detect_same_user_near_duplicate(
        embeddings=[emb, emb],
        existing_profile=profile,
        threshold=0.9,
    )
    assert result.is_duplicate is True

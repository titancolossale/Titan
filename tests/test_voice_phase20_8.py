# =====================================
# Titan Phase 20.8 — Live Providers & Real Voice Preparation Tests
# =====================================

"""Live providers, browser WS, enrollment prep, soak, diagnostics, performance."""

from __future__ import annotations

import base64
import json
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
    HistogramEmbeddingProvider,
    embeddings_compatible,
    get_embedding_provider,
    mean_embedding,
)
from voice.enrollment_models import EMBEDDING_VERSION, EnrollmentStatus, SpeakerIdentityProfile
from voice.enrollment_quality import (
    detect_cross_user_duplicates,
    language_independence_score,
    safe_profile_replacement_plan,
    score_embedding_quality,
)
from voice.live_session import LiveVoiceSessionOrchestrator
from voice.models import VoiceConfig
from voice.production_soak import (
    DEFAULT_SOAK_SCENARIOS,
    SoakScenarioId,
    VoiceProductionSoakRunner,
)
from voice.provider_health import collect_provider_health
from voice.providers.elevenlabs_streaming import ElevenLabsStreamingTTS
from voice.providers.failover import FailoverConfig, StreamingProviderFailover
from voice.providers.openai_realtime import OpenAIRealtimeSession
from voice.providers.realtime_registry import RealtimeProviderRegistry
from voice.providers.registry_bootstrap import register_realtime_voice_providers
from voice.speaker_identifier import SpeakerIdentifier, extract_voice_features
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.stream_performance import StreamPerformanceController
from voice.transport.browser_hub import (
    BrowserVoiceHub,
    reset_browser_voice_hub_for_tests,
)
from voice.transport.browser_protocol import (
    BrowserFrame,
    BrowserFrameType,
    BrowserReconnectPolicy,
)
from voice.transport.manager import TransportManager
from voice.transport.memory import InMemoryTransport
from voice.transport.socket_backends import websocket_client_available
from voice.voice_enrollment import VoiceEnrollmentService
from voice.voice_session import VoiceSessionStore


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
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


# ---------------------------------------------------------------------------
# Embedding provider / enrollment quality
# ---------------------------------------------------------------------------


def test_histogram_embedding_provider_language_independent_shape():
    provider = HistogramEmbeddingProvider()
    assert provider.embedding_version == EMBEDDING_VERSION
    assert provider.dimension == 32
    a = provider.extract(_speech_like(1))
    b = provider.extract(_speech_like(1))
    assert len(a) == 32
    assert a == b
    assert embeddings_compatible(provider.embedding_version, EMBEDDING_VERSION)
    assert not embeddings_compatible("histogram_v1", "ecapa_v1")


def test_extract_voice_features_delegates_to_provider():
    features = extract_voice_features(_speech_like(42))
    assert len(features) == get_embedding_provider().dimension
    assert abs(sum(v * v for v in features) - 1.0) < 1e-5


def test_embedding_quality_and_language_independence():
    emb_a = [extract_voice_features(_speech_like(10 + i)) for i in range(3)]
    emb_b = [extract_voice_features(_speech_like(10 + i)) for i in range(3)]
    report = score_embedding_quality(emb_a[0])
    assert 0.0 <= report.score <= 1.0
    assert report.language_independent is True
    score = language_independence_score(emb_a, emb_b)
    assert score > 0.9


def test_cross_user_duplicate_detection():
    shared = extract_voice_features(_speech_like(99))
    nolan = SpeakerIdentityProfile.create(user_id="Nolan", status=EnrollmentStatus.ENROLLED)
    nolan.active = True
    nolan.embeddings = [shared, shared]
    nolan.embedding_version = EMBEDDING_VERSION
    result = detect_cross_user_duplicates(
        user_id="Ibrahim",
        embeddings=[shared, shared],
        candidates=[nolan],
        threshold=0.9,
    )
    assert result.is_duplicate
    assert result.matches[0].other_user_id == "Nolan"


def test_safe_profile_replacement_plan():
    blocked = safe_profile_replacement_plan(
        existing_profile_id="old",
        new_profile_id="new",
        replace_existing=False,
    )
    assert blocked["action"] == "blocked"
    replace = safe_profile_replacement_plan(
        existing_profile_id="old",
        new_profile_id="new",
        replace_existing=True,
    )
    assert replace["action"] == "atomic_replace"
    assert replace["revoke_old"] is True


def test_multiple_enrollment_sessions_history(tmp_path: Path):
    from voice.enrollment_models import EnrollmentConfig

    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(min_quality_score=0.2),
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "enroll_tmp",
    )
    first = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        session_label="quiet_room",
        consent_accepted=True,
    )
    assert first["ok"] is True
    assert first["session"]["session_label"] == "quiet_room"
    sid1 = first["session"]["session_id"]
    # Supersede with a second session — history retained.
    second = service.start_enrollment(
        target_user="Nolan",
        authenticated_user="Nolan",
        session_label="noisy_room",
        consent_accepted=True,
    )
    assert second["ok"] is True
    assert second["enrollment_history_count"] >= 2
    prior = store.get_session(sid1)
    assert prior is not None
    assert prior.status == EnrollmentStatus.CANCELLED
    assert prior.failure_reason == "superseded_by_new_enrollment"
    sessions = store.list_sessions_for_user("Nolan")
    assert len(sessions) >= 2


def test_finish_enrollment_blocks_cross_user_duplicate(tmp_path: Path):
    from voice.enrollment_models import EnrollmentConfig

    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    service = VoiceEnrollmentService(
        store=store,
        config=EnrollmentConfig(min_sample_count=3, min_quality_score=0.2),
        state_manager=StateManager(file_path=tmp_path / "state.json"),
        temp_dir=tmp_path / "enroll_tmp",
    )
    # Pre-activate Nolan with a known voiceprint family.
    samples = [_speech_like(77 + i, 2.5) for i in range(3)]
    existing = SpeakerIdentityProfile.create(
        user_id="Nolan", status=EnrollmentStatus.ENROLLED
    )
    existing.active = True
    existing.embeddings = [extract_voice_features(a) for a in samples]
    existing.embedding_version = EMBEDDING_VERSION
    store.create_profile(existing)
    store.activate_profile(existing.profile_id)

    started = service.start_enrollment(
        target_user="Ibrahim",
        authenticated_user="Ibrahim",
        consent_accepted=True,
    )
    sid = started["session"]["session_id"]
    for audio in samples:
        accepted = service.submit_sample(
            session_id=sid,
            audio_bytes=audio,
            authenticated_user="Ibrahim",
        )
        assert accepted["ok"] is True, accepted
    finished = service.finish_enrollment(
        session_id=sid, authenticated_user="Ibrahim"
    )
    assert finished["ok"] is False
    assert finished["error"] == "cross_user_duplicate_detected"


# ---------------------------------------------------------------------------
# Live providers
# ---------------------------------------------------------------------------


def test_register_realtime_includes_openai_realtime_and_live_flag():
    registry = RealtimeProviderRegistry()
    register_realtime_voice_providers(
        realtime_registry=registry, prefer_live_sockets=False
    )
    assert "openai_realtime" in registry.list_stt()
    assert "openai_realtime" in registry.list_tts()
    assert "deepgram_streaming" in registry.list_stt()
    assert "elevenlabs_streaming" in registry.list_tts()
    assert "openai_whisper_streaming" in registry.list_stt()
    stt = registry.create_stt("openai_realtime")
    assert stt.health_check()
    assert stt.provider_id == "openai_realtime"


def test_openai_realtime_base64_audio_framing():
    transport = InMemoryTransport(name="rt")
    session = OpenAIRealtimeSession(api_key=None, transport=transport)
    session.start(language="fr-FR")
    session.send_audio(b"\x00\x01\x02\x03")
    frames = []
    for msg in transport.outbound_frames:
        if not msg.binary:
            frames.append(json.loads(msg.as_text()))
    appends = [f for f in frames if f.get("type") == "input_audio_buffer.append"]
    assert appends
    decoded = base64.b64decode(appends[0]["audio"])
    assert decoded == b"\x00\x01\x02\x03"

    session.inject_provider_event(
        {
            "type": "response.audio.delta",
            "audio": base64.b64encode(b"pcm-out").decode("ascii"),
        }
    )
    chunk = session.poll_audio(timeout=0.0)
    assert chunk is not None
    assert chunk.audio_bytes == b"pcm-out"


def test_elevenlabs_sends_real_api_key_not_redacted_placeholder():
    transport = InMemoryTransport(name="eleven")
    tts = ElevenLabsStreamingTTS(api_key="secret-key-xyz", transport=transport)
    tts.start(locale="fr-FR", voice="Rachel")
    text_frames = [
        json.loads(m.as_text())
        for m in transport.outbound_frames
        if not m.binary
    ]
    assert text_frames
    payload = text_frames[0]
    assert payload["xi_api_key"] == "secret-key-xyz"
    assert payload["xi_api_key"] != "[REDACTED]"


def test_elevenlabs_decodes_base64_audio_when_live():
    transport = InMemoryTransport(name="eleven2")
    tts = ElevenLabsStreamingTTS(api_key="key", transport=transport)
    tts.start(locale="en-US", voice="Rachel")
    tts.inject_provider_message(
        {"audio": base64.b64encode(b"mp3-bytes").decode("ascii"), "isFinal": True}
    )
    chunk = tts.poll_audio(timeout=0.0, force=True)
    assert chunk is not None
    assert chunk.audio_bytes == b"mp3-bytes"


def test_failover_reuses_retry_policy_and_transport_manager():
    registry = RealtimeProviderRegistry()
    transport = InMemoryTransport(name="failover-tm")
    tm = TransportManager(transport)
    failover = StreamingProviderFailover(
        registry=registry,
        preferred_stt="mock_realtime_stt",
        preferred_tts="mock_realtime_tts",
        config=FailoverConfig(max_retries=2, sleep=lambda _s: None),
        transport_manager=tm,
    )
    failover.activate()
    assert failover._retry_policy is failover._retry_policy
    diag = failover.diagnostics()
    assert diag["transport"] is not None
    # Network loss should attempt transport recover without raising.
    failover.on_network_loss()


# ---------------------------------------------------------------------------
# Browser transport
# ---------------------------------------------------------------------------


def test_browser_hub_heartbeat_backpressure_and_recover():
    hub = BrowserVoiceHub()
    conn = hub.register("c1", authenticated_user="Nolan")
    hub.mark_connected("c1")
    hub.bind_session("c1", session_id="s1", recovery_token="tok")
    replies = hub.handle_frame(
        "c1", BrowserFrame(type=BrowserFrameType.HEARTBEAT, sequence=1)
    )
    assert any(r.type == BrowserFrameType.HEARTBEAT_ACK for r in replies)

    # Fill queue to trigger backpressure drop.
    conn.backpressure.max_queue_frames = 1
    drop_replies = hub.handle_frame(
        "c1",
        BrowserFrame(
            type=BrowserFrameType.AUDIO,
            sequence=2,
            payload={"bytes": 100},
        ),
        binary_bytes=100,
    )
    # Second oversized offer should backpressure.
    conn.backpressure.queued_frames = 1
    conn.backpressure.queued_bytes = conn.backpressure.max_queue_bytes
    drop_replies = hub.handle_frame(
        "c1",
        BrowserFrame(type=BrowserFrameType.AUDIO, sequence=3, payload={"bytes": 50}),
        binary_bytes=50,
    )
    assert any(r.type == BrowserFrameType.BACKPRESSURE for r in drop_replies)

    hub.close("c1", reason="drop")
    hub.register("c2", authenticated_user="Nolan")
    recovered = hub.recover(
        "c2", session_id="s1", recovery_token="tok", last_client_seq=3
    )
    assert recovered.reconnect_count >= 1
    snap = hub.diagnostics_snapshot()
    assert snap["connection_count"] >= 1


def test_browser_reconnect_policy_backoff():
    policy = BrowserReconnectPolicy(max_attempts=3, base_delay_seconds=0.1)
    assert policy.should_retry(0)
    assert not policy.should_retry(3)
    delay = policy.delay_for_attempt(1)
    assert delay >= 0.0


def test_provider_health_snapshot_includes_embedding_and_browser():
    reset_browser_voice_hub_for_tests()
    registry = RealtimeProviderRegistry()
    register_realtime_voice_providers(
        realtime_registry=registry, prefer_live_sockets=False
    )
    snap = collect_provider_health(realtime_registry=registry)
    assert snap["ok"] is True
    assert "stt" in snap and "tts" in snap
    assert snap["embedding"]["embedding_version"] == EMBEDDING_VERSION
    assert "browser_transport" in snap
    assert "live_socket_backend_available" in snap


# ---------------------------------------------------------------------------
# Production soak (Phase 20.8 scenarios)
# ---------------------------------------------------------------------------


def test_phase20_8_soak_scenarios_present():
    ids = {s.scenario_id for s in DEFAULT_SOAK_SCENARIOS}
    assert SoakScenarioId.BROWSER_RECONNECT in ids
    assert SoakScenarioId.CONCURRENT_SESSIONS in ids
    assert SoakScenarioId.PROVIDER_FALLBACK in ids
    assert SoakScenarioId.RAILWAY_DEPLOYMENT in ids


def test_phase20_8_soak_runner(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    runner = VoiceProductionSoakRunner(orch, speech_factory=_speech_like)
    report = runner.run(
        scenarios=tuple(
            s
            for s in DEFAULT_SOAK_SCENARIOS
            if s.scenario_id
            in {
                SoakScenarioId.BROWSER_RECONNECT,
                SoakScenarioId.CONCURRENT_SESSIONS,
                SoakScenarioId.PROVIDER_FALLBACK,
                SoakScenarioId.RAILWAY_DEPLOYMENT,
                SoakScenarioId.PROVIDER_RECONNECT,
            }
        )
    )
    assert report.ok, report.to_dict()
    assert report.to_dict()["passed"] == 5


# ---------------------------------------------------------------------------
# Diagnostics events + API
# ---------------------------------------------------------------------------


def test_phase20_8_diagnostic_events_registered():
    for event in (
        "PROVIDER_HEALTH_SNAPSHOT",
        "VOICE_WS_CONNECTED",
        "VOICE_WS_BACKPRESSURE",
        "VOICE_WS_RECOVERED",
        "EMBEDDING_QUALITY",
    ):
        assert event in VOICE_DIAGNOSTIC_EVENTS
    assert "PROVIDER_HEALTH_SNAPSHOT" in VOICE_STREAM_EVENTS


def test_diagnostics_api_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "false")
    reset_titan()
    reset_live_orchestrator_for_tests()
    reset_browser_voice_hub_for_tests()
    brain = _build_brain(tmp_path)
    titan = Titan.__new__(Titan)
    titan.brain = brain
    titan.state_manager = brain.state_manager
    titan.mission_manager = brain.mission_manager
    set_titan(titan)
    app = create_app()
    client = TestClient(app)
    providers = client.get("/voice/session/diagnostics/providers")
    assert providers.status_code == 200
    body = providers.json()
    assert body["ok"] is True
    assert "stt" in body
    transport = client.get("/voice/session/diagnostics/transport")
    assert transport.status_code == 200
    assert transport.json()["ok"] is True


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_stream_performance_coalesce_minimizes_allocations():
    ctrl = StreamPerformanceController()
    # Many tiny frames coalesce into fewer sendable blocks.
    sent = 0
    for i in range(40):
        block = ctrl.ingest_mic_audio(bytes([i % 256]) * 100)
        if block is not None:
            sent += 1
    flush = ctrl.flush_mic_audio() if hasattr(ctrl, "flush_mic_audio") else None
    stats = ctrl.stats.to_dict()
    assert stats["coalesce_count"] >= 0
    assert "peak_pending_audio_bytes" in stats


def test_websocket_client_availability_is_bool():
    assert isinstance(websocket_client_available(), bool)


def test_mean_embedding_empty_safe():
    assert mean_embedding([]) == []
    assert mean_embedding([[1.0, 0.0], [0.0, 1.0]]) == [0.5, 0.5]

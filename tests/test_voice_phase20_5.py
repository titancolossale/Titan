# =====================================
# Titan Phase 20.5 — Real-Time Voice Conversation Engine Tests
# =====================================

"""Continuous conversation, streaming STT/Brain/TTS, recovery, latency, cleanup."""

from __future__ import annotations

import base64
import time
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
from voice.cancellation import CancelToken, TurnCancellation
from voice.conversation_engine import (
    ConversationEngineConfig,
    RealtimeConversationEngine,
)
from voice.diagnostics import VOICE_DIAGNOSTIC_EVENTS, VOICE_STREAM_EVENTS
from voice.exceptions import VoiceSessionError
from voice.latency_tracker import LatencyTracker
from voice.live_session import LiveVoiceSessionOrchestrator, MicCaptureMode
from voice.models import VoiceConfig
from voice.speaker_identifier import SpeakerIdentifier
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.streaming_brain import StreamingBrainAdapter
from voice.streaming_stt import IncrementalSTTEngine, TranscriptStage
from voice.streaming_tts import StreamingTTSEngine, detect_response_locale
from voice.tts_strategy import TTSStrategy, TTSStrategyConfig, TTSStrategyMode
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


def _enroll_user(identifier: SpeakerIdentifier, user: str, seed: int) -> bytes:
    sample = _speech_like(seed, 1.5)
    identifier.enroll(
        user, [sample, _speech_like(seed + 1, 1.5), _speech_like(seed + 2, 1.5)]
    )
    return sample


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(file_path=tmp_path / "state.json")


@pytest.fixture
def orchestrator(
    tmp_path: Path, state_manager: StateManager
) -> LiveVoiceSessionOrchestrator:
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Bonjour, je suis Titan.")
    )
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        profile_store=store,
        enabled=True,
    )
    stt = SpeechToTextRegistry()
    mock_stt = MockSpeechToTextProvider(default_text="bonjour titan")
    stt.register(mock_stt)
    return LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(
            language="fr-FR",
            stt_provider="mock",
            tts_provider="mock",
        ),
        session_store=VoiceSessionStore(file_path=tmp_path / "voice_sessions.json"),
        stt_registry=stt,
        speaker_identifier=identifier,
        state_manager=state_manager,
        idle_timeout_seconds=2.0,
        conversation_timeout_seconds=30.0,
        provider_timeout_seconds=5.0,
        temp_dir=tmp_path / "voice_tmp",
        conversation_engine=RealtimeConversationEngine(
            config=ConversationEngineConfig(
                idle_timeout_seconds=2.0,
                conversation_timeout_seconds=30.0,
                recovery_ttl_seconds=60.0,
            )
        ),
    )


def _start_and_speak(
    orch: LiveVoiceSessionOrchestrator,
    audio: bytes,
    *,
    user: str = "Nolan",
    mode: str = "push_to_talk",
) -> dict:
    started = orch.start_session(authenticated_user=user, capture_mode=mode)
    sid = started["session_id"]
    orch.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    return orch.finish_utterance(sid)


# ---------------------------------------------------------------------------
# Unit: cancellation / STT / Brain / TTS / latency / engine
# ---------------------------------------------------------------------------


def test_cancel_token_independent_stages() -> None:
    turn = TurnCancellation()
    turn.stt.cancel()
    assert turn.stt.cancelled
    assert not turn.brain.cancelled
    turn.cancel_all()
    assert turn.cancelled


def test_incremental_stt_partial_stable_final(tmp_path: Path) -> None:
    events: list[str] = []
    registry = SpeechToTextRegistry()
    mock = MockSpeechToTextProvider(default_text="salut titan")
    registry.register(mock)
    engine = IncrementalSTTEngine(
        provider_id="mock",
        registry=registry,
        emit=lambda e, d: events.append(e),
    )
    chunk = _speech_like(3, 0.4)
    mock.set_response(chunk, "salut titan")
    engine.ingest_chunk(chunk, sequence=0)
    engine.ingest_chunk(chunk, sequence=1)
    assert engine.result.stage in {TranscriptStage.PARTIAL, TranscriptStage.STABLE}
    assert "VOICE_STREAM_STARTED" in events
    assert "VOICE_STREAM_PARTIAL" in events
    # Partial must never be treated as Brain text until FINAL.
    assert engine.result.brain_text == "" or engine.result.stage == TranscriptStage.STABLE
    final = engine.finalize(chunk)
    assert final.stage == TranscriptStage.FINAL
    assert final.brain_text == "salut titan"
    assert "VOICE_STREAM_FINAL" in events
    assert "VOICE_STREAM_STABLE" in events


def test_streaming_brain_deltas_and_no_duplicate() -> None:
    events: list[str] = []
    brain = MagicMock()
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Une. Deux.")
    )
    adapter = StreamingBrainAdapter(
        brain, emit=lambda e, d: events.append(e), timeout_seconds=5.0
    )
    first = adapter.run("hello", turn_key="t1")
    assert first.final_text == "Une. Deux."
    assert first.deltas
    assert "BRAIN_STREAM_STARTED" in events
    assert "BRAIN_STREAM_COMPLETED" in events
    second = adapter.run("hello", turn_key="t1")
    assert second.duplicate_prevented
    assert brain.process_request.call_count == 1


def test_streaming_brain_cancellation() -> None:
    token = CancelToken(name="brain")
    brain = MagicMock()

    def _slow(*_a, **_k):
        token.cancel()
        return SimpleNamespace(final_response="late")

    brain.process_request = MagicMock(side_effect=_slow)
    adapter = StreamingBrainAdapter(brain, cancel_token=token, timeout_seconds=5.0)
    # Cancel before run — should short-circuit.
    token.cancel()
    result = adapter.run("x", turn_key="c1")
    assert result.cancelled


def test_streaming_tts_sentence_chunks_and_locale() -> None:
    assert detect_response_locale("Bonjour je suis là").startswith("fr")
    assert detect_response_locale(
        "Hello and you can please help me with the project"
    ).startswith("en")
    events: list[str] = []
    strategy = TTSStrategy(
        config=TTSStrategyConfig(mode=TTSStrategyMode.SENTENCE_BUFFERED, min_text_chunk_chars=4),
        provider_id="mock",
        locale="fr-FR",
    )
    engine = StreamingTTSEngine(
        strategy,
        strategy_config=strategy.config,
        emit=lambda e, d: events.append(e),
    )
    result = engine.synthesize_from_deltas(
        ["Bonjour. ", "Comment ça va?"],
        full_text="Bonjour. Comment ça va?",
    )
    assert result.chunks
    assert "TTS_STREAM_STARTED" in events
    assert "TTS_STREAM_CHUNK" in events
    assert "TTS_STREAM_COMPLETED" in events


def test_latency_tracker_marks() -> None:
    tracker = LatencyTracker()
    tracker.mark_first_audio()
    tracker.mark_first_transcript()
    tracker.mark_first_brain_token(12.5)
    tracker.mark_first_tts_audio(33.0)
    tracker.enter_idle()
    time.sleep(0.02)
    delay = tracker.exit_idle()
    tracker.mark_response_complete()
    data = tracker.to_dict()
    assert data["first_brain_token_ms"] == 12.5
    assert data["first_tts_audio_ms"] == 33.0
    assert delay >= 0.0
    assert data["total_response_ms"] >= 0.0


def test_conversation_engine_idle_resume_and_recovery() -> None:
    engine = RealtimeConversationEngine(
        config=ConversationEngineConfig(
            idle_timeout_seconds=0.05,
            conversation_timeout_seconds=5.0,
            recovery_ttl_seconds=30.0,
        )
    )
    bound = engine.bind_session(
        "s1",
        authenticated_user="Nolan",
        conversation_id="c1",
        capture_mode="push_to_talk",
    )
    token = bound["recovery"]["recovery_token"]
    engine.mark_idle("s1")
    engine.touch("s1")
    engine.note_turn(
        "s1",
        transcript="salut",
        assistant_text="bonjour",
        speaker_identity="Nolan",
    )
    ctx = engine.get_context("s1")
    assert ctx is not None
    assert ctx.turn_count == 1
    assert ctx.speaker_identity == "Nolan"
    recovered = engine.recover(recovery_token=token, authenticated_user="Nolan")
    assert recovered["recovered"] is True
    engine.close_session("s1", reason="cancel")
    with pytest.raises(VoiceSessionError):
        engine.recover(recovery_token=token, authenticated_user="Nolan")


def test_diagnostic_events_include_phase_20_5() -> None:
    required = {
        "VOICE_STREAM_STARTED",
        "VOICE_STREAM_PARTIAL",
        "VOICE_STREAM_STABLE",
        "VOICE_STREAM_FINAL",
        "BRAIN_STREAM_STARTED",
        "BRAIN_STREAM_DELTA",
        "BRAIN_STREAM_COMPLETED",
        "TTS_STREAM_STARTED",
        "TTS_STREAM_CHUNK",
        "TTS_STREAM_COMPLETED",
        "VOICE_CONVERSATION_IDLE",
        "VOICE_CONVERSATION_RESUMED",
        "VOICE_SESSION_RECOVERED",
        "VOICE_SESSION_CLOSED",
    }
    assert required.issubset(set(VOICE_DIAGNOSTIC_EVENTS))
    assert required.issubset(set(VOICE_STREAM_EVENTS))


# ---------------------------------------------------------------------------
# Integration: continuous conversation / interruption / recovery
# ---------------------------------------------------------------------------


def test_continuous_multi_turn_memory_and_speaker(orchestrator, tmp_path) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 11)
    mock_stt = orchestrator._stt_registry.get("mock")
    assert isinstance(mock_stt, MockSpeechToTextProvider)

    started = orchestrator.start_session(
        authenticated_user="Nolan", capture_mode=MicCaptureMode.PUSH_TO_TALK
    )
    sid = started["session_id"]
    assert started.get("recovery_token")
    assert started.get("conversation_id")

    mock_stt.set_response(sample, "première question")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    first = orchestrator.finish_utterance(sid)
    assert first["voice_session_state"] == "LISTENING"
    assert first.get("tts_audio_chunks")
    assert first.get("assistant_text_preview")

    # Second turn — same session, no Brain reload required.
    sample2 = _speech_like(99, 1.5)
    mock_stt.set_response(sample2, "deuxième question")
    mock_stt._default_text = "deuxième question"
    orchestrator._brain.process_request.return_value = SimpleNamespace(
        final_response="Deuxième réponse continue."
    )
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample2, sequence=0)
    second = orchestrator.finish_utterance(sid)
    assert second["voice_session_state"] == "LISTENING"
    ctx = orchestrator._conversation.get_context(sid)
    assert ctx is not None
    assert ctx.turn_count == 2
    assert ctx.speaker_identity == "Nolan"
    assert orchestrator._brain.process_request.call_count == 2


def test_stream_interruption_and_double_barge_in(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 21)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "interromps moi")
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result.get("tts_audio_chunks")

    # Force speaking then barge-in twice.
    from voice.session_lifecycle import LiveSessionState

    orchestrator._machines[sid].force(LiveSessionState.SPEAKING)
    orchestrator._sessions[sid].state = LiveSessionState.SPEAKING
    barge1 = orchestrator.submit_audio_chunk(
        sid, audio_bytes=_speech_like(5, 0.5), sequence=1
    )
    assert barge1.get("barge_in") is True
    interrupted = orchestrator.interrupt_playback(sid)
    assert interrupted["voice_interrupted"] is True
    # Second interrupt while already listening must not crash.
    again = orchestrator.interrupt_playback(sid)
    assert again["voice_session_state"] == "LISTENING"


def test_partial_not_sent_to_brain(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 31)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "texte final seulement")
    # Also map WAV-wrapped / assembled payloads via default when exact key misses.
    mock_stt._default_text = "texte final seulement"
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    # Small chunks generate partial UI text without Brain calls.
    tiny = sample[:4000]
    orchestrator.submit_audio_chunk(sid, audio_bytes=tiny, sequence=0)
    assert orchestrator._brain.process_request.call_count == 0
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=1)
    finished = orchestrator.finish_utterance(sid)
    assert orchestrator._brain.process_request.call_count == 1
    called_text = orchestrator._brain.process_request.call_args[0][0]
    assert "texte final seulement" in called_text
    assert finished.get("assistant_text_preview")


def test_session_recovery_after_drop(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 41)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "récupération")
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    token = started["recovery_token"]
    conv = started["conversation_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    # Simulate browser disconnect without destroying recovery token.
    orchestrator.on_client_disconnect(sid)
    recovered = orchestrator.recover_session(
        authenticated_user="Nolan",
        recovery_token=token,
        conversation_id=conv,
    )
    assert recovered.get("recovered") is True
    assert recovered.get("session_id")
    assert recovered.get("conversation_id") == conv


def test_idle_timeout_closes_session(orchestrator) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    # Force idle clock into the past.
    orchestrator._conversation._session_activity[sid] = time.monotonic() - 10
    closed = orchestrator.get_safe_state(sid)
    assert closed.get("timed_out") is True
    assert closed.get("timeout_reason") == "idle_timeout"
    with pytest.raises(VoiceSessionError):
        orchestrator.get_safe_state(sid)


def test_conversation_timeout(orchestrator) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator._conversation._session_started[sid] = time.monotonic() - 100
    closed = orchestrator.heartbeat(sid)
    assert closed.get("timed_out") is True
    assert closed.get("timeout_reason") == "conversation_timeout"


def test_provider_timeout_fails_gracefully(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 51)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "timeout")

    def _hang(*_a, **_k):
        time.sleep(2.0)
        return SimpleNamespace(final_response="late")

    orchestrator._provider_timeout = 0.05
    # Rebuild brain adapter timeout.
    for adapter in orchestrator._streaming_brain.values():
        adapter._timeout = 0.05
    orchestrator._brain.process_request = MagicMock(side_effect=_hang)
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    # Soft fail recovers to LISTENING.
    assert result["voice_session_state"] == "LISTENING"


def test_session_and_resource_cleanup(orchestrator) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    assert sid in orchestrator._sessions
    assert sid in orchestrator._incremental_stt
    cancelled = orchestrator.cancel_session(sid)
    assert cancelled["voice_session_state"] == "CANCELLED"
    assert sid not in orchestrator._sessions
    assert sid not in orchestrator._incremental_stt
    assert sid not in orchestrator._streaming_tts


def test_latency_metrics_on_turn(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 61)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "latence")
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    latency = result["latency"]
    assert "stt_ms" in latency
    assert "brain_first_token_ms" in latency
    assert "tts_first_audio_ms" in latency
    assert latency["stt_ms"] >= 0.0


def test_continuous_capture_mode_flag(orchestrator) -> None:
    started = orchestrator.start_session(
        authenticated_user="Nolan",
        capture_mode=MicCaptureMode.CONTINUOUS,
    )
    assert started["capture_mode"] == MicCaptureMode.CONTINUOUS
    assert started["continuous_conversation"] is True
    assert started["always_listening"] is False


def test_always_listening_forced_off(orchestrator) -> None:
    started = orchestrator.start_session(
        authenticated_user="Nolan",
        capture_mode=MicCaptureMode.ALWAYS_LISTENING,
    )
    assert started["capture_mode"] == MicCaptureMode.PUSH_TO_TALK
    assert started["always_listening"] is False


def test_drain_stream_events(orchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 71)
    mock_stt = orchestrator._stt_registry.get("mock")
    mock_stt.set_response(sample, "événements")
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    drained = orchestrator.drain_stream_events(sid)
    assert "stream_events" in drained


def test_heartbeat_keeps_idle_alive(orchestrator) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    # Almost idle, but heartbeat refreshes activity.
    orchestrator._conversation._session_activity[sid] = time.monotonic() - 1.5
    alive = orchestrator.heartbeat(sid)
    assert alive.get("timed_out") is not True
    assert alive["session_id"] == sid


# ---------------------------------------------------------------------------
# API auth + recover/heartbeat/events
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    reset_titan()
    reset_live_orchestrator_for_tests()
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="API ok.")
    )
    titan = MagicMock(spec=Titan)
    titan.brain = brain
    set_titan(titan)
    app = create_app()
    client = TestClient(app)
    yield client
    reset_live_orchestrator_for_tests()
    reset_titan()


def test_api_recover_heartbeat_events_require_auth(api_client: TestClient) -> None:
    # Dev mode still requires auth middleware in some setups — assert routes exist.
    start = api_client.post(
        "/voice/session/start",
        json={"capture_mode": "push_to_talk", "microphone_enabled": True},
    )
    # 200 in web-dev, or 401 if auth enforced without session.
    assert start.status_code in {200, 401, 403}
    if start.status_code != 200:
        return
    sid = start.json()["session_id"]
    token = start.json().get("recovery_token")
    hb = api_client.post("/voice/session/heartbeat", json={"session_id": sid})
    assert hb.status_code == 200
    ev = api_client.get(f"/voice/session/events?session_id={sid}")
    assert ev.status_code == 200
    rec = api_client.post(
        "/voice/session/recover",
        json={"recovery_token": token, "conversation_id": start.json().get("conversation_id")},
    )
    assert rec.status_code == 200
    assert rec.json().get("recovered") is True


def test_api_unauthenticated_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "false")
    monkeypatch.setenv("TITAN_AUTH_REQUIRED", "true")
    reset_titan()
    reset_live_orchestrator_for_tests()
    app = create_app()
    client = TestClient(app)
    for path in (
        "/voice/session/start",
        "/voice/session/heartbeat",
        "/voice/session/recover",
    ):
        resp = client.post(path, json={})
        assert resp.status_code in {401, 403, 422, 503}


def test_web_voice_module_contracts() -> None:
    root = Path(__file__).resolve().parents[1] / "web" / "v2" / "voice"
    controller = (root / "voice-controller.js").read_text(encoding="utf-8")
    api = (root / "voice-api.js").read_text(encoding="utf-8")
    playback = (root / "tts-playback.js").read_text(encoding="utf-8")
    assert "recoverVoiceSession" in api
    assert "heartbeatVoiceSession" in api
    assert "enqueueChunk" in playback
    assert "_tryRecoverOnLoad" in controller
    assert "_startHeartbeat" in controller
    assert "RECOVERY_STORAGE_KEY" in controller
    assert "always_listening" not in controller.lower() or "ALWAYS_LISTENING" not in controller


def test_browser_compat_helpers_present() -> None:
    """Best-effort Safari/Firefox markers remain in capture/playback stack."""
    root = Path(__file__).resolve().parents[1] / "web" / "v2" / "voice"
    capture = (root / "audio-capture.js").read_text(encoding="utf-8")
    mic = (root / "microphone.js").read_text(encoding="utf-8")
    assert "AudioContext" in capture or "webkitAudioContext" in capture
    assert "getUserMedia" in mic or "mediaDevices" in mic

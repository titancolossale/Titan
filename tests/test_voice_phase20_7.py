# =====================================
# Titan Phase 20.7 — Live Voice Experience & Production Soak Tests
# =====================================

"""Mic calibration, silence, conversation flow, soak scenarios, diagnostics."""

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
from voice.conversation_flow import ConversationFlowController, FlowPhase
from voice.diagnostics import VOICE_DIAGNOSTIC_EVENTS, VOICE_STREAM_EVENTS
from voice.latency_tracker import LatencyTracker
from voice.live_session import LiveVoiceSessionOrchestrator, MicCaptureMode
from voice.mic_calibration import (
    MicCalibrationConfig,
    MicCalibrator,
    estimate_clipping_ratio,
    estimate_recommended_gain,
)
from voice.models import VoiceConfig
from voice.production_soak import (
    DEFAULT_SOAK_SCENARIOS,
    SoakScenarioId,
    VoiceProductionSoakRunner,
)
from voice.session_stats import VoiceSessionStatistics
from voice.silence_detector import (
    SilenceDecision,
    SilenceDetector,
    SilenceDetectorConfig,
)
from voice.speaker_identifier import SpeakerIdentifier
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.vad import VADConfig, VoiceActivityDetector
from voice.voice_session import VoiceSessionStore
import time


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _silence(seconds: float = 0.25) -> bytes:
    n = int(16000 * seconds)
    return bytes([128] * n)


def _click(seed: int = 1) -> bytes:
    # Very short low-energy burst — false speech candidate.
    n = int(16000 * 0.08)
    return bytes(((seed * 3 + i) % 20) + 118 for i in range(n))


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
    registry = SpeechToTextRegistry()
    registry.register(MockSpeechToTextProvider(default_text="bonjour titan"))
    return LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        session_store=VoiceSessionStore(file_path=tmp_path / "voice_sessions.json"),
        stt_registry=registry,
        speaker_identifier=identifier,
        state_manager=state_manager,
        temp_dir=tmp_path / "voice_tmp",
        idle_timeout_seconds=30.0,
        conversation_timeout_seconds=600.0,
    )


# ---------------------------------------------------------------------------
# Mic calibration
# ---------------------------------------------------------------------------


def test_mic_calibrator_noise_floor_gain_clipping() -> None:
    cal = MicCalibrator(
        MicCalibrationConfig(window_seconds=0.4, min_chunks=4, low_volume_rms=0.5)
    )
    cal.start()
    assert cal.active
    for i in range(6):
        snap = cal.feed(_speech_like(10 + i, 0.1), vad_config=VADConfig())
    assert snap.calibrated
    assert snap.noise_floor >= 0.0
    assert snap.speech_threshold > snap.noise_floor
    assert snap.gain_estimate >= 0.5
    assert snap.sample_count >= 4


def test_mic_calibrator_clipping_and_gain_helpers() -> None:
    clipped = bytes([0, 255] * 800)
    assert estimate_clipping_ratio(clipped, sample_width=1) > 0.5
    assert estimate_recommended_gain(0.05, target=0.2) == pytest.approx(4.0)
    assert estimate_recommended_gain(0.4, target=0.2) == pytest.approx(0.5)


def test_orchestrator_mic_calibration_applies_thresholds(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    started = orchestrator.start_session(
        authenticated_user="Nolan", capture_mode=MicCaptureMode.PUSH_TO_TALK
    )
    sid = started["session_id"]
    begin = orchestrator.start_mic_calibration(sid)
    assert begin["calibrating"] is True
    for i in range(12):
        orchestrator.feed_mic_calibration(sid, audio_bytes=_speech_like(20 + i, 0.15))
    finished = orchestrator.finish_mic_calibration(sid)
    assert finished["mic_calibration"]["calibrated"] is True
    silence = orchestrator._silence_detectors[sid]
    assert silence.vad.config.speech_start_threshold > 0
    stats = orchestrator.get_session_statistics(sid)
    assert stats["calibration_count"] >= 1
    orchestrator.cancel_session(sid)


# ---------------------------------------------------------------------------
# Silence detection
# ---------------------------------------------------------------------------


def test_silence_detector_end_of_turn() -> None:
    detector = SilenceDetector(
        config=SilenceDetectorConfig(
            end_of_turn_silence_seconds=0.3,
            min_utterance_duration_seconds=0.2,
            false_speech_max_seconds=0.05,
        ),
        vad_config=VADConfig(
            silence_timeout_seconds=0.3,
            min_utterance_duration_seconds=0.2,
            speech_start_threshold=0.02,
            speech_end_threshold=0.01,
        ),
    )
    # Speech then silence past timeout.
    detector.process_chunk(_speech_like(1, 0.4))
    end = None
    for _ in range(20):
        result = detector.process_chunk(_silence(0.05))
        if result.decision == SilenceDecision.END_OF_TURN:
            end = result
            break
    assert end is not None
    assert end.decision == SilenceDecision.END_OF_TURN


def test_silence_detector_false_speech_and_long_pause() -> None:
    detector = SilenceDetector(
        config=SilenceDetectorConfig(
            end_of_turn_silence_seconds=0.15,
            long_pause_timeout_seconds=0.4,
            false_speech_max_seconds=0.2,
            false_speech_max_energy=0.5,
            min_utterance_duration_seconds=0.3,
        ),
        vad_config=VADConfig(
            silence_timeout_seconds=0.15,
            min_utterance_duration_seconds=0.3,
            speech_start_threshold=0.015,
            speech_end_threshold=0.008,
        ),
    )
    detector.process_chunk(_click(3))
    ended = None
    for _ in range(15):
        result = detector.process_chunk(_silence(0.05))
        if result.decision in {SilenceDecision.FALSE_SPEECH, SilenceDecision.END_OF_TURN}:
            ended = result
            break
    assert ended is not None

    detector.reset()
    long_pause = None
    for _ in range(20):
        result = detector.process_chunk(_silence(0.05))
        if result.decision == SilenceDecision.LONG_PAUSE:
            long_pause = result
            break
    assert long_pause is not None


# ---------------------------------------------------------------------------
# Conversation flow
# ---------------------------------------------------------------------------


def test_conversation_flow_barge_in_resume_confirmation() -> None:
    flow = ConversationFlowController()
    flow.bind_continuity("tok")
    flow.on_listening()
    flow.on_speech_start()
    assert flow.phase == FlowPhase.USER_SPEAKING
    flow.on_natural_pause()
    flow.on_speech_end()
    flow.on_assistant_speaking()
    assert flow.can_accept_barge_in()
    info = flow.on_barge_in()
    assert info["interrupted"] is True
    # Immediately after barge-in, debounce blocks a second attempt.
    assert flow.can_accept_barge_in() is False
    flow.last_barge_in_at = time.monotonic() - 1.0
    assert flow.can_accept_barge_in() is True
    flow.resume_ready_at = 0.0
    assert flow.resume_after_interruption() is True
    prompt = flow.confirmation_prompt(locale="fr-FR")
    assert "Nolan" in prompt or "Ibrahim" in prompt
    flow.on_awaiting_confirmation()
    assert flow.note_confirmation_retry() is True
    flow.clear_confirmation()
    completed = flow.on_turn_complete()
    assert completed.turn_index == 0
    assert flow.turn.turn_index == 1


def test_interrupt_resume_and_debounce(orchestrator: LiveVoiceSessionOrchestrator) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    audio = _speech_like(40, 1.0)
    orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    finished = orchestrator.finish_utterance(sid)
    # Force speaking then interrupt.
    from voice.session_lifecycle import LiveSessionState

    live = orchestrator._sessions[sid]
    orchestrator._machines[sid].force(LiveSessionState.SPEAKING)
    live.state = LiveSessionState.SPEAKING
    flow = orchestrator._flow_controllers[sid]
    flow.on_assistant_speaking()
    first = orchestrator.interrupt_playback(sid)
    assert first.get("voice_interrupted") or first.get("voice_session_state")
    # Debounced second interrupt should not crash.
    second = orchestrator.interrupt_playback(sid)
    assert "session_id" in second
    orchestrator.cancel_session(sid)


# ---------------------------------------------------------------------------
# Session stats + latency
# ---------------------------------------------------------------------------


def test_session_stats_and_latency_marks(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    started = orchestrator.start_session(authenticated_user="Nolan")
    sid = started["session_id"]
    orchestrator.submit_audio_chunk(
        sid, audio_bytes=_speech_like(50, 1.0), sequence=0, timestamp_ms=12.5
    )
    orchestrator.finish_utterance(sid)
    stats = orchestrator.get_session_statistics(sid)
    assert stats["turn_count"] >= 1
    assert "averages" in stats
    tracker = LatencyTracker()
    tracker.mark_mic_latency(12.5)
    tracker.mark_speech_duration(900)
    tracker.mark_turn_duration(1500)
    tracker.mark_mic_calibration(40)
    tracker.mark_interruption_recovery(15)
    data = tracker.to_dict()
    assert data["mic_latency_ms"] == 12.5
    assert data["speech_duration_ms"] == 900
    assert data["mic_calibration_ms"] == 40
    orchestrator.cancel_session(sid)


def test_voice_session_statistics_aggregates() -> None:
    stats = VoiceSessionStatistics(session_id="s1")
    stats.record_calibration(noise_floor=0.01, gain_estimate=1.5, clipping=True)
    stats.record_turn(
        turn_index=0,
        speech_duration_ms=800,
        turn_duration_ms=1200,
        mic_latency_ms=10,
        provider_latency_ms=200,
        brain_latency_ms=300,
        tts_latency_ms=150,
        interrupted=True,
    )
    stats.note_end_of_turn()
    stats.note_long_pause()
    stats.note_false_speech()
    stats.note_provider_reconnect()
    stats.note_network_interruption()
    stats.note_speaker_switch()
    payload = stats.to_dict()
    assert payload["clipping_warnings"] == 1
    assert payload["barge_in_count"] == 1
    assert payload["provider_reconnects"] == 1
    assert payload["averages"]["avg_brain_latency_ms"] == 300


# ---------------------------------------------------------------------------
# Production soak
# ---------------------------------------------------------------------------


def test_default_soak_scenarios_cover_required_ids() -> None:
    ids = {s.scenario_id for s in DEFAULT_SOAK_SCENARIOS}
    assert SoakScenarioId.LONG_CONVERSATION in ids
    assert SoakScenarioId.PROVIDER_RECONNECT in ids
    assert SoakScenarioId.NETWORK_INTERRUPTION in ids
    assert SoakScenarioId.RAPID_START_STOP in ids
    assert SoakScenarioId.MULTIPLE_SESSIONS in ids
    assert SoakScenarioId.ENROLLMENT_PERSISTENCE in ids
    assert SoakScenarioId.SPEAKER_SWITCHING in ids


def test_production_soak_runner_all_scenarios(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    runner = VoiceProductionSoakRunner(orchestrator, speech_factory=_speech_like)
    # Use smaller turn counts for speed while covering every scenario type.
    slim = tuple(
        type(s)(
            scenario_id=s.scenario_id,
            title=s.title,
            description=s.description,
            turns=2 if s.turns > 2 else s.turns,
            require_reconnect=s.require_reconnect,
            require_network_drop=s.require_network_drop,
            require_enrollment=s.require_enrollment,
            require_speaker_switch=s.require_speaker_switch,
            rapid_cycles=3 if s.rapid_cycles > 3 else s.rapid_cycles,
        )
        for s in DEFAULT_SOAK_SCENARIOS
    )
    report = runner.run(slim)
    assert report.ok, report.to_dict()
    assert report.to_dict()["passed"] == len(slim)


# ---------------------------------------------------------------------------
# Diagnostics membership
# ---------------------------------------------------------------------------


def test_phase20_7_diagnostic_events_registered() -> None:
    for name in (
        "VOICE_MIC_CALIBRATION_STARTED",
        "VOICE_MIC_CALIBRATION_COMPLETED",
        "VOICE_MIC_LOW_VOLUME",
        "VOICE_MIC_CLIPPING",
        "VOICE_END_OF_TURN",
        "VOICE_LONG_PAUSE",
        "VOICE_FALSE_SPEECH_REJECTED",
        "VOICE_NATURAL_PAUSE",
        "VOICE_RESUME_AFTER_INTERRUPT",
        "VOICE_TURN_TIMING",
        "VOICE_SESSION_STATS",
        "VOICE_SOAK_SCENARIO",
    ):
        assert name in VOICE_DIAGNOSTIC_EVENTS
    for name in (
        "VOICE_MIC_CALIBRATION_COMPLETED",
        "VOICE_END_OF_TURN",
        "VOICE_RESUME_AFTER_INTERRUPT",
    ):
        assert name in VOICE_STREAM_EVENTS


# ---------------------------------------------------------------------------
# API contracts
# ---------------------------------------------------------------------------


def test_calibrate_and_stats_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_VOICE_ENABLED", "true")
    reset_titan()
    reset_live_orchestrator_for_tests()
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="ok")
    )
    titan = Titan.__new__(Titan)
    titan.brain = brain
    titan.state_manager = StateManager(file_path=tmp_path / "state.json")
    set_titan(titan)
    client = TestClient(create_app())
    start = client.post(
        "/voice/session/start",
        json={"capture_mode": "push_to_talk", "microphone_enabled": True},
    )
    assert start.status_code == 200
    sid = start.json()["session_id"]
    cal = client.post("/voice/session/calibrate/start", json={"session_id": sid})
    assert cal.status_code == 200
    import base64

    chunk = base64.b64encode(_speech_like(70, 0.2)).decode("ascii")
    fed = client.post(
        "/voice/session/calibrate/chunk",
        json={"session_id": sid, "audio_base64": chunk, "sequence": 0},
    )
    assert fed.status_code == 200
    fin = client.post("/voice/session/calibrate/finish", json={"session_id": sid})
    assert fin.status_code == 200
    stats = client.get(f"/voice/session/stats?session_id={sid}")
    assert stats.status_code == 200
    assert "turn_count" in stats.json()
    client.post("/voice/session/cancel", json={"session_id": sid})
    reset_live_orchestrator_for_tests()
    reset_titan()


def test_web_voice_calibration_exports_present() -> None:
    root = Path(__file__).resolve().parents[1] / "web" / "v2" / "voice"
    audio = (root / "audio-capture.js").read_text(encoding="utf-8")
    mic = (root / "microphone.js").read_text(encoding="utf-8")
    api = (root / "voice-api.js").read_text(encoding="utf-8")
    assert "estimateMicMetrics" in audio
    assert "estimateRecommendedGain" in audio
    assert "microphonePermissionFlow" in mic
    assert "autoGainControl" in mic
    assert "startMicCalibration" in api
    assert "getVoiceSessionStats" in api

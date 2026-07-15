# =====================================
# Titan Voice Runtime Tests
# =====================================

"""Tests for Voice Runtime V1 — session, providers, Brain integration, interruptions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.natural_language_orchestrator import OrchestrationResult
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager
from voice.audio_devices import AudioDeviceManager, MockAudioCapture, MockAudioPlayback
from voice.exceptions import VoiceConfigurationError, VoiceDeviceError, VoiceSessionError, VoiceStateError
from voice.models import ConversationMode, VoiceConfig, VoiceState
from voice.speech_to_text import (
    MockSpeechToTextProvider,
    SpeechToTextRegistry,
    TranscriptionResult,
)
from voice.text_to_speech import MockTextToSpeechProvider, TextToSpeechRegistry
from voice.voice_runtime import VoiceRuntime, voice_config_from_settings
from voice.voice_session import VoiceSessionStore


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


def _make_runtime(
    tmp_path: Path,
    *,
    config: VoiceConfig | None = None,
) -> VoiceRuntime:
    brain = _build_brain(tmp_path)
    store = VoiceSessionStore(file_path=tmp_path / "voice_sessions.json")
    capture = MockAudioCapture(audio_payload=b"user-audio")
    playback = MockAudioPlayback()
    stt = SpeechToTextRegistry()
    mock_stt = MockSpeechToTextProvider(default_text="bonjour titan")
    mock_stt.set_response(b"user-audio", "bonjour titan")
    stt.register(mock_stt)
    tts = TextToSpeechRegistry()
    tts.register(MockTextToSpeechProvider())
    return VoiceRuntime(
        brain,
        config=config or VoiceConfig(),
        session_store=store,
        stt_registry=stt,
        tts_registry=tts,
        audio_capture=capture,
        audio_playback=playback,
    )


@pytest.fixture
def voice_runtime(tmp_path: Path) -> VoiceRuntime:
    return _make_runtime(tmp_path)


# --- Session lifecycle ---


def test_session_create_and_end(voice_runtime: VoiceRuntime, tmp_path: Path) -> None:
    session = voice_runtime.start_session()
    assert session.active
    assert session.conversation_id
    assert voice_runtime.state == VoiceState.IDLE

    store = VoiceSessionStore(file_path=tmp_path / "voice_sessions.json")
    loaded = store.get_session(session.conversation_id)
    assert loaded is not None
    assert loaded.language == "fr-FR"

    ended = voice_runtime.end_session()
    assert ended is not None
    assert not ended.active
    assert voice_runtime.session is None


def test_session_resume(voice_runtime: VoiceRuntime) -> None:
    first = voice_runtime.start_session(conversation_id="sess-1")
    voice_runtime.end_session()

    voice_runtime.start_session(resume=True)
    # ended session should not resume — new session created
    assert voice_runtime.session is not None
    assert voice_runtime.session.conversation_id != first.conversation_id


def test_session_persistence_updates_history(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    voice_runtime.process_text_turn("Salut Titan")

    session = voice_runtime.session
    assert session is not None
    assert len(session.conversation_history) == 1
    assert session.last_response


def test_end_unknown_session_raises(tmp_path: Path) -> None:
    store = VoiceSessionStore(file_path=tmp_path / "voice_sessions.json")
    with pytest.raises(VoiceSessionError):
        store.end_session("missing-id")


# --- Provider abstraction ---


def test_stt_registry_unknown_provider() -> None:
    registry = SpeechToTextRegistry()
    with pytest.raises(VoiceConfigurationError):
        registry.get("nonexistent")


def test_tts_registry_mock_synthesis() -> None:
    registry = TextToSpeechRegistry()
    provider = registry.resolve("mock")
    result = provider.synthesize("Bonjour", locale="fr-FR", voice="default")
    assert result.audio_bytes
    assert result.provider_id == "mock"


def test_stt_mock_transcription() -> None:
    provider = MockSpeechToTextProvider()
    provider.set_response(b"abc", "test phrase")
    result = provider.transcribe(b"abc", locale="fr-FR")
    assert result.text == "test phrase"
    assert isinstance(result, TranscriptionResult)


# --- Brain integration ---


def test_process_text_turn_calls_brain_process_request(
    voice_runtime: VoiceRuntime,
) -> None:
    voice_runtime.start_session()
    with patch.object(
        voice_runtime._brain,
        "process_request",
        return_value=OrchestrationResult(
            request_analysis=MagicMock(),
            detected_intent=MagicMock(),
            pipeline_decision=MagicMock(),
            systems_used=MagicMock(),
            reasoning_summary="test",
            confidence=0.9,
            final_response="Voici ma réponse.",
        ),
    ) as mock_process:
        mock_process.return_value.final_response = "Voici ma réponse."
        result = voice_runtime.process_text_turn("Quelle heure est-il ?")

    mock_process.assert_called_once_with("Quelle heure est-il ?")
    assert result.assistant_text == "Voici ma réponse."
    assert result.metrics.brain_seconds >= 0


def test_brain_is_only_planning_entry(voice_runtime: VoiceRuntime) -> None:
    """Voice Runtime must not call think() or orchestrator directly."""
    voice_runtime.start_session()
    brain = voice_runtime._brain
    with patch.object(brain, "process_request") as mock_pr:
        mock_pr.return_value = MagicMock(final_response="ok")
        with patch.object(brain, "think") as mock_think:
            with patch.object(brain.natural_language_orchestrator, "process") as mock_nlo:
                voice_runtime.process_text_turn("hello")
    mock_think.assert_not_called()
    mock_nlo.assert_not_called()
    mock_pr.assert_called_once()


# --- Conversation flow ---


def test_listen_once_full_pipeline(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    result = voice_runtime.listen_once()
    assert result.user_text == "bonjour titan"
    assert result.assistant_text
    assert voice_runtime.state == VoiceState.IDLE


def test_process_audio_turn(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    result = voice_runtime.process_audio_turn(b"user-audio")
    assert result.metrics.transcription_seconds >= 0
    assert result.user_text == "bonjour titan"


def test_push_to_talk_flow(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    voice_runtime.push_to_talk_start()
    assert voice_runtime.state == VoiceState.LISTENING
    result = voice_runtime.push_to_talk_stop()
    assert result.user_text == "bonjour titan"


def test_continuous_listen(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    results = voice_runtime.listen_continuous(max_turns=2)
    assert len(results) == 2


def test_empty_utterance_raises(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    with pytest.raises(VoiceConfigurationError):
        voice_runtime.process_text_turn("   ")


# --- Interruptions ---


def test_interrupt_speaking_stops_playback(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    playback = voice_runtime._playback
    assert isinstance(playback, MockAudioPlayback)
    voice_runtime.interrupt_speaking()
    assert playback.stop_count >= 1


def test_queue_and_flush_responses(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    voice_runtime.queue_response("Message en file")
    results = voice_runtime.flush_response_queue()
    assert len(results) == 1
    assert results[0].user_text == "Message en file"


def test_interrupt_before_speak_queues_response(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    voice_runtime.interrupt_speaking()
    result = voice_runtime.process_text_turn("test interrupt")
    assert result.interrupted


# --- State transitions ---


def test_state_transitions_idle_to_thinking(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    assert voice_runtime.state == VoiceState.IDLE
    voice_runtime.process_text_turn("hello")
    assert voice_runtime.state == VoiceState.IDLE


def test_pause_and_resume(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    voice_runtime.push_to_talk_start()
    voice_runtime.pause()
    assert voice_runtime.state == VoiceState.PAUSED
    voice_runtime.resume()
    assert voice_runtime.state == VoiceState.IDLE


def test_pause_from_idle_raises(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    with pytest.raises(VoiceStateError):
        voice_runtime.pause()


# --- Configuration ---


def test_voice_config_from_settings(monkeypatch) -> None:
    monkeypatch.setattr("config.settings.TITAN_VOICE_LOCALE", "en-US")
    monkeypatch.setattr("config.settings.TITAN_VOICE_STT_PROVIDER", "mock")
    monkeypatch.setattr("config.settings.TITAN_VOICE_TTS_PROVIDER", "mock")
    monkeypatch.setattr("config.settings.TITAN_VOICE_MICROPHONE", "mic-1")
    monkeypatch.setattr("config.settings.TITAN_VOICE_SPEAKER", "spk-1")
    monkeypatch.setattr("config.settings.TITAN_VOICE_SILENCE_TIMEOUT", 3.5)
    monkeypatch.setattr("config.settings.TITAN_VOICE_CONVERSATION_MODE", "push_to_talk")
    monkeypatch.setattr("config.settings.TITAN_VOICE_VOICE", "alloy")
    monkeypatch.setattr("config.settings.TITAN_VOICE_VOLUME", 0.8)
    monkeypatch.setattr("config.settings.TITAN_VOICE_TTS_RATE", 1.1)

    cfg = voice_config_from_settings()
    assert cfg.language == "en-US"
    assert cfg.conversation_mode == ConversationMode.PUSH_TO_TALK
    assert cfg.silence_timeout_seconds == 3.5


def test_get_status(voice_runtime: VoiceRuntime) -> None:
    voice_runtime.start_session()
    status = voice_runtime.get_status()
    assert status["state"] == VoiceState.IDLE.value
    assert "mock" in status["stt_providers"]
    assert status["session"] is not None


# --- Audio devices ---


def test_audio_device_manager_resolve() -> None:
    manager = AudioDeviceManager()
    mic = manager.resolve_input("default")
    spk = manager.resolve_output("default")
    assert mic.is_input
    assert spk.is_output


def test_unknown_device_raises() -> None:
    manager = AudioDeviceManager()
    with pytest.raises(VoiceDeviceError):
        manager.resolve_input("nonexistent-device")


# --- Errors ---


def test_stt_provider_failure_wrapped(tmp_path: Path) -> None:
    class FailingSTT(MockSpeechToTextProvider):
        def transcribe(self, audio_bytes: bytes, *, locale: str, **kwargs):
            raise RuntimeError("provider down")

    registry = SpeechToTextRegistry()
    registry.register(FailingSTT())
    runtime = _make_runtime(tmp_path)
    runtime._stt_registry = registry
    runtime.start_session()
    from voice.exceptions import VoiceProviderError

    with pytest.raises(VoiceProviderError):
        runtime.process_audio_turn(b"x")

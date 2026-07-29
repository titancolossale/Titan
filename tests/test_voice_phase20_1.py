# =====================================
# Titan Phase 20.1 — Voice Provider + Runtime Integration
# =====================================

"""OpenAI provider adapters and speaker-gated VoiceRuntime behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager
from voice.audio_devices import MockAudioCapture, MockAudioPlayback
from voice.models import VoiceConfig
from voice.providers.openai_stt import OpenAIWhisperSpeechToTextProvider
from voice.providers.openai_tts import OpenAITextToSpeechProvider
from voice.providers.registry_bootstrap import register_default_voice_providers
from voice.speaker_identifier import UNKNOWN_SPEAKER_PROMPT, SpeakerIdentifier
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.text_to_speech import MockTextToSpeechProvider, TextToSpeechRegistry
from voice.voice_manager import VoiceManager
from voice.voice_runtime import VoiceRuntime
from voice.voice_session import VoiceSessionStore


def _audio_pattern(seed: int, size: int = 2048) -> bytes:
    return bytes((seed + i * 13) % 256 for i in range(size))


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
    speaker: SpeakerIdentifier,
    default_text: str = "bonjour titan",
) -> VoiceRuntime:
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Réponse brain.")
    )
    store = VoiceSessionStore(file_path=tmp_path / "voice_sessions.json")
    audio = _audio_pattern(7)
    capture = MockAudioCapture(audio_payload=audio)
    playback = MockAudioPlayback()
    stt = SpeechToTextRegistry()
    mock_stt = MockSpeechToTextProvider(default_text=default_text)
    mock_stt.set_response(audio, default_text)
    stt.register(mock_stt)
    tts = TextToSpeechRegistry()
    tts.register(MockTextToSpeechProvider())
    return VoiceRuntime(
        brain,
        config=VoiceConfig(),
        session_store=store,
        stt_registry=stt,
        tts_registry=tts,
        audio_capture=capture,
        audio_playback=playback,
        speaker_identifier=speaker,
        register_live_providers=False,
    )


def test_openai_whisper_provider_uses_injected_client() -> None:
    client = MagicMock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(text="bonjour")
    provider = OpenAIWhisperSpeechToTextProvider(client=client, model="whisper-1")
    result = provider.transcribe(b"fake-wav", locale="fr-FR")
    assert result.text == "bonjour"
    assert result.provider_id == "openai_whisper"
    client.audio.transcriptions.create.assert_called_once()


def test_openai_tts_provider_uses_injected_client() -> None:
    client = MagicMock()
    client.audio.speech.create.return_value = SimpleNamespace(content=b"AUDIO")
    provider = OpenAITextToSpeechProvider(client=client, model="gpt-4o-mini-tts")
    result = provider.synthesize("Salut", locale="fr-FR", voice="default")
    assert result.audio_bytes == b"AUDIO"
    assert result.provider_id == "openai_tts"
    assert result.voice == "alloy"


def test_register_default_voice_providers() -> None:
    stt = SpeechToTextRegistry()
    tts = TextToSpeechRegistry()
    register_default_voice_providers(stt_registry=stt, tts_registry=tts)
    assert "openai_whisper" in stt.list_providers()
    assert "openai_tts" in tts.list_providers()
    assert "mock" in stt.list_providers()


def test_unknown_speaker_blocks_brain(tmp_path: Path) -> None:
    speaker = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        enabled=True,
        min_confidence=0.9,
    )
    runtime = _make_runtime(tmp_path, speaker=speaker, default_text="quelle heure est-il")
    runtime.start_session()
    result = runtime.listen_once()
    assert result.brain_invoked is False
    assert UNKNOWN_SPEAKER_PROMPT in result.assistant_text
    assert result.speaker_confirmation_required is True
    runtime._brain.process_request.assert_not_called()


def test_enrolled_speaker_binds_user_and_invokes_brain(tmp_path: Path) -> None:
    speaker = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        enabled=True,
        min_confidence=0.5,
    )
    audio = _audio_pattern(7)
    speaker.enroll("Ibrahim", [audio])
    runtime = _make_runtime(tmp_path, speaker=speaker, default_text="bonjour titan")
    runtime.start_session()
    result = runtime.listen_once()
    assert result.brain_invoked is True
    assert result.speaker_identity == "Ibrahim"
    assert runtime._brain.context_manager.current_user == "Ibrahim"
    runtime._brain.process_request.assert_called_once()


def test_confirmation_phrase_binds_without_brain_task(tmp_path: Path) -> None:
    speaker = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        enabled=True,
        min_confidence=0.85,
    )
    # Enroll a dissimilar envelope so live capture does not auto-match.
    speaker.enroll("Nolan", [bytes([0] * 2048)])
    runtime = _make_runtime(tmp_path, speaker=speaker, default_text="je suis Ibrahim")
    runtime.start_session()
    result = runtime.listen_once()
    assert result.brain_invoked is False
    assert "Ibrahim" in result.assistant_text
    assert runtime._brain.context_manager.current_user == "Ibrahim"
    runtime._brain.process_request.assert_not_called()


def test_voice_manager_exposes_speaker_identification() -> None:
    manager = VoiceManager()
    config = manager.get_config()
    assert "speaker_identification" in config
    assert "enabled" in config["speaker_identification"]
    caps = manager.get_capabilities()
    assert "openai_whisper" in caps.live_stt_providers
    assert "openai_tts" in caps.live_tts_providers

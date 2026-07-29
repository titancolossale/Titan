# =====================================
# Titan Phase 20.3 — Live Voice Session Tests
# =====================================

"""Live session orchestration, VAD, speaker gate, barge-in, privacy, API auth."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
from voice.diagnostics import emit_voice_diagnostic, sanitize_diagnostic_payload
from voice.enrollment_models import RecognitionBand
from voice.live_session import (
    RESTRICTED_UNKNOWN_PREFIX,
    LiveVoiceSessionOrchestrator,
)
from voice.models import VoiceConfig
from voice.session_lifecycle import LiveSessionState
from voice.speaker_identifier import SpeakerIdentifier, SpeakerIdentity
from voice.speaker_profile_store import SpeakerProfileStore
from voice.speech_segmenter import SpeechSegmenter
from voice.speech_to_text import MockSpeechToTextProvider, SpeechToTextRegistry
from voice.tts_strategy import (
    TTSStrategy,
    TTSStrategyConfig,
    TTSStrategyMode,
    clean_text_for_speech,
)
from voice.vad import VADConfig, VADEvent, VoiceActivityDetector
from voice.voice_session import VoiceSessionStore


def _speech_like(seed: int, seconds: float = 1.25) -> bytes:
    n = int(16000 * seconds)
    return bytes(((seed * 37 + i * 17) % 180) + 40 for i in range(n))


def _silence(seconds: float = 1.25) -> bytes:
    n = int(16000 * seconds)
    return bytes([128] * n)


def _short_click() -> bytes:
    return bytes([200, 10, 200, 10, 180])


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
    identifier.enroll(user, [sample, _speech_like(seed + 1, 1.5), _speech_like(seed + 2, 1.5)])
    return sample


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(file_path=tmp_path / "state.json")


@pytest.fixture
def orchestrator(tmp_path: Path, state_manager: StateManager) -> LiveVoiceSessionOrchestrator:
    brain = _build_brain(tmp_path)
    brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="Bonjour, voici ma réponse claire.")
    )
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        profile_store=store,
        min_confidence=0.72,
        medium_confidence=0.55,
        ambiguity_delta=0.05,
    )
    stt = SpeechToTextRegistry()
    mock_stt = MockSpeechToTextProvider(default_text="bonjour titan")
    stt.register(mock_stt)
    return LiveVoiceSessionOrchestrator(
        brain,
        config=VoiceConfig(stt_provider="mock", tts_provider="mock", language="fr-FR"),
        vad_config=VADConfig(
            min_utterance_duration_seconds=0.2,
            max_utterance_duration_seconds=8.0,
            silence_timeout_seconds=0.3,
            speech_start_threshold=0.02,
            sensitivity=0.7,
        ),
        session_store=VoiceSessionStore(file_path=tmp_path / "sessions.json"),
        stt_registry=stt,
        speaker_identifier=identifier,
        state_manager=state_manager,
        temp_dir=tmp_path / "voice_live_tmp",
        identity_confirmation_timeout_seconds=30.0,
        provider_timeout_seconds=5.0,
        tts_strategy_config=TTSStrategyConfig(
            mode=TTSStrategyMode.SENTENCE_BUFFERED,
            min_text_chunk_chars=10,
        ),
    )


def _start(orch: LiveVoiceSessionOrchestrator, user: str = "Nolan") -> dict:
    return orch.start_session(authenticated_user=user, capture_mode="push_to_talk")


# --- VAD / segmentation -------------------------------------------------------


def test_silence_is_rejected() -> None:
    vad = VoiceActivityDetector(VADConfig(min_utterance_duration_seconds=0.2))
    ok, reason = vad.validate_utterance(_silence(1.0))
    assert ok is False
    assert reason == "pure_silence"


def test_very_short_audio_is_rejected() -> None:
    vad = VoiceActivityDetector(VADConfig(min_utterance_duration_seconds=0.35))
    ok, reason = vad.validate_utterance(_short_click())
    assert ok is False
    assert reason in {"too_short", "accidental_click", "pure_silence"}


def test_malformed_audio_is_rejected() -> None:
    vad = VoiceActivityDetector()
    ok, reason = vad.validate_utterance(b"RIFF" + b"\x00" * 20)
    assert ok is False
    assert reason == "malformed_audio"


def test_valid_chunks_build_ordered_utterance() -> None:
    segmenter = SpeechSegmenter(
        vad=VoiceActivityDetector(
            VADConfig(min_utterance_duration_seconds=0.2, sensitivity=0.8)
        )
    )
    chunks = [_speech_like(3, 0.4), _speech_like(4, 0.4), _speech_like(5, 0.4)]
    for i, chunk in enumerate(chunks):
        segmenter.force_append(chunk, sequence=i)
    assembled = segmenter.finalize()
    assert assembled == b"".join(chunks)


def test_duplicate_chunks_ignored() -> None:
    segmenter = SpeechSegmenter()
    chunk = _speech_like(9, 0.5)
    segmenter.force_append(chunk, sequence=1)
    segmenter.force_append(chunk, sequence=1)
    assert segmenter.buffered_bytes == len(chunk)


def test_speech_start_and_end_detected() -> None:
    vad = VoiceActivityDetector(
        VADConfig(
            speech_start_threshold=0.02,
            speech_end_threshold=0.01,
            silence_timeout_seconds=0.15,
            sensitivity=0.8,
            min_utterance_duration_seconds=0.1,
        )
    )
    start = vad.process_chunk(_speech_like(11, 0.2))
    assert start.event in {VADEvent.SPEECH_START, VADEvent.SPEECH_CONTINUE}
    # Feed silence until end.
    ended = False
    for _ in range(20):
        result = vad.process_chunk(_silence(0.05))
        if result.event == VADEvent.SPEECH_END:
            ended = True
            break
    assert ended


def test_max_utterance_duration_enforced() -> None:
    vad = VoiceActivityDetector(
        VADConfig(
            max_utterance_duration_seconds=0.5,
            speech_start_threshold=0.01,
            sensitivity=0.9,
            silence_timeout_seconds=5.0,
        )
    )
    first = vad.process_chunk(_speech_like(2, 0.3))
    assert first.event == VADEvent.SPEECH_START or first.in_speech
    second = vad.process_chunk(_speech_like(2, 0.4))
    assert second.rejected is True
    assert second.reject_reason == "max_utterance_duration"


# --- Speaker gating -----------------------------------------------------------


def test_high_confidence_nolan_binds(orchestrator: LiveVoiceSessionOrchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 21)
    session = _start(orchestrator)
    sid = session["session_id"]
    orchestrator._speaker_identifier.reload()
    # Force identify path with enrolled sample via finish after chunk.
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "salut titan")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_current_speaker"] == "Nolan"
    assert result["voice_identity_confidence_band"] == RecognitionBand.HIGH.value
    orchestrator._brain.process_request.assert_called()
    call_text = orchestrator._brain.process_request.call_args[0][0]
    assert RESTRICTED_UNKNOWN_PREFIX not in call_text


def test_high_confidence_ibrahim_binds(orchestrator: LiveVoiceSessionOrchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Ibrahim", 41)
    session = _start(orchestrator, user="Ibrahim")
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "bonjour")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_current_speaker"] == "Ibrahim"


def test_medium_confidence_requires_confirmation(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enroll_user(orchestrator._speaker_identifier, "Nolan", 55)
    session = _start(orchestrator)
    sid = session["session_id"]
    audio = _speech_like(99, 1.2)

    def fake_identify(_audio: bytes):
        return SimpleNamespace(
            identity=SpeakerIdentity.UNKNOWN,
            confidence=0.60,
            requires_confirmation=True,
            reason="medium_confidence",
            matched_user="Nolan",
            recognition_band=RecognitionBand.MEDIUM,
            is_known=False,
            threshold=0.72,
        )

    monkeypatch.setattr(orchestrator._speaker_identifier, "identify", fake_identify)
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(audio, "hello")
    orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_session_state"] == LiveSessionState.WAITING_FOR_IDENTITY_CONFIRMATION.value
    assert result["pending_identity_confirmation"]["predicted_user"] == "Nolan"
    orchestrator._brain.process_request.assert_not_called()


def test_low_confidence_remains_unknown(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _start(orchestrator)
    sid = session["session_id"]
    audio = _speech_like(77, 1.2)

    def fake_identify(_audio: bytes):
        return SimpleNamespace(
            identity=SpeakerIdentity.UNKNOWN,
            confidence=0.2,
            requires_confirmation=True,
            reason="low_confidence",
            matched_user=None,
            recognition_band=RecognitionBand.LOW,
            is_known=False,
            threshold=0.72,
        )

    monkeypatch.setattr(orchestrator._speaker_identifier, "identify", fake_identify)
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(audio, "question generique")
    orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_current_speaker"] is None
    call_text = orchestrator._brain.process_request.call_args[0][0]
    assert RESTRICTED_UNKNOWN_PREFIX in call_text


def test_ambiguous_never_auto_selects(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _start(orchestrator)
    sid = session["session_id"]
    audio = _speech_like(12, 1.2)

    def fake_identify(_audio: bytes):
        return SimpleNamespace(
            identity=SpeakerIdentity.UNKNOWN,
            confidence=0.8,
            requires_confirmation=True,
            reason="ambiguous_match",
            matched_user=None,
            recognition_band=RecognitionBand.AMBIGUOUS,
            is_known=False,
            threshold=0.72,
        )

    monkeypatch.setattr(orchestrator._speaker_identifier, "identify", fake_identify)
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(audio, "salut")
    orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_current_speaker"] is None
    assert result["pending_identity_confirmation"]["confidence_band"] == "ambiguous"
    orchestrator._brain.process_request.assert_not_called()


def test_unknown_speaker_restricted_context(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_low_confidence_remains_unknown(orchestrator, monkeypatch)


def test_revoked_profile_never_matches(tmp_path: Path) -> None:
    store = SpeakerProfileStore(file_path=tmp_path / "profiles.json")
    identifier = SpeakerIdentifier(profile_store=store)
    sample = _speech_like(33, 1.5)
    identifier.enroll("Nolan", [sample, _speech_like(34, 1.5), _speech_like(35, 1.5)])
    active = store.get_active_profile("Nolan")
    assert active is not None
    store.revoke_profile(active.profile_id)
    identifier.reload()
    result = identifier.identify(sample)
    assert result.is_known is False


# --- Brain / TTS / barge-in ---------------------------------------------------


def test_stt_enters_brain_pipeline(orchestrator: LiveVoiceSessionOrchestrator) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 61)
    session = _start(orchestrator)
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "quelle heure est-il")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    assert orchestrator._brain.process_request.called
    assert "quelle heure" in orchestrator._brain.process_request.call_args[0][0]


def test_brain_response_reaches_tts(orchestrator: LiveVoiceSessionOrchestrator) -> None:
    events: list[str] = []
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 71)
    session = orchestrator.start_session(
        authenticated_user="Nolan",
        stream_callback=lambda e, _d: events.append(e),
    )
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "bonjour")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    assert "VOICE_TTS_STARTED" in events
    assert "VOICE_AUDIO_CHUNK" in events
    assert "VOICE_TTS_COMPLETED" in events


def test_sentence_buffered_tts_preserves_order() -> None:
    strategy = TTSStrategy(
        config=TTSStrategyConfig(mode=TTSStrategyMode.SENTENCE_BUFFERED, min_text_chunk_chars=5),
        provider_id="mock",
        locale="fr-FR",
    )
    deltas = ["Bonjour Nolan. ", "Voici la suite. ", "Fin."]
    outputs = strategy.synthesize_streaming_deltas(deltas)
    texts = [t for t, _ in outputs]
    assert texts == sorted(texts, key=lambda t: "".join(deltas).find(t.split()[0]))
    joined = " ".join(texts)
    assert "Bonjour" in joined and "suite" in joined and "Fin" in joined


def test_markdown_and_code_cleaned() -> None:
    raw = "# Titre\n```python\nprint(1)\n```\n**Salut** [lien](http://x)"
    cleaned = clean_text_for_speech(raw)
    assert "```" not in cleaned
    assert "print" not in cleaned
    assert "**" not in cleaned
    assert "http" not in cleaned
    assert "Salut" in cleaned


def test_barge_in_stops_playback_and_starts_new_utterance(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 81)
    session = _start(orchestrator)
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "premiere")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    live = orchestrator._sessions[sid]
    # Force speaking state then barge-in.
    orchestrator._machines[sid].force(LiveSessionState.SPEAKING)
    live.state = LiveSessionState.SPEAKING
    new_audio = _speech_like(82, 1.0)
    result = orchestrator.submit_audio_chunk(sid, audio_bytes=new_audio, sequence=10)
    assert result.get("barge_in") is True or result["voice_speech_detected"] is True
    assert live.interrupted is True
    assert live.state in {
        LiveSessionState.CAPTURING,
        LiveSessionState.SPEECH_DETECTED,
        LiveSessionState.LISTENING,
    }


def test_interrupted_response_does_not_duplicate_persistence(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 91)
    session = _start(orchestrator)
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "msg")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    orchestrator.finish_utterance(sid)
    conv_id = orchestrator._sessions[sid].conversation_id
    assert conv_id
    before = len(orchestrator._session_store.get_session(conv_id).conversation_history)
    orchestrator.interrupt_playback(sid)
    after = len(orchestrator._session_store.get_session(conv_id).conversation_history)
    assert after == before


def test_cancellation_releases_resources(
    orchestrator: LiveVoiceSessionOrchestrator,
) -> None:
    session = _start(orchestrator)
    sid = session["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=_speech_like(1, 0.5), sequence=0)
    orchestrator.cancel_session(sid)
    assert sid not in orchestrator._sessions
    assert sid not in orchestrator._segmenters


def test_client_disconnect_cleans_buffers(
    orchestrator: LiveVoiceSessionOrchestrator, tmp_path: Path
) -> None:
    session = _start(orchestrator)
    sid = session["session_id"]
    orchestrator.submit_audio_chunk(sid, audio_bytes=_speech_like(2, 0.5), sequence=0)
    # Simulate temp file
    temp = tmp_path / "voice_live_tmp" / f"{sid}_x.bin"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_bytes(b"abc")
    orchestrator._temp_files[sid].append(temp)
    orchestrator.on_client_disconnect(sid)
    assert sid not in orchestrator._sessions
    assert not temp.exists()


def test_provider_timeout_does_not_leave_session_stuck(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 101)
    session = _start(orchestrator)
    sid = session["session_id"]

    def boom(*_a, **_k):
        raise TimeoutError("slow")

    monkeypatch.setattr(
        "voice.live_session.transcribe_audio",
        boom,
    )
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "x")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_session_state"] == LiveSessionState.LISTENING.value
    assert orchestrator._sessions[sid].brain_lock is False


def test_brain_lock_returns_idle_after_failure(
    orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 111)
    session = _start(orchestrator)
    sid = session["session_id"]
    orchestrator._brain.process_request = MagicMock(side_effect=RuntimeError("brain down"))
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "x")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    result = orchestrator.finish_utterance(sid)
    assert result["voice_session_state"] == LiveSessionState.LISTENING.value
    assert orchestrator._sessions[sid].brain_lock is False


def test_no_raw_audio_or_embeddings_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="titan.voice.diagnostics"):
        emit_voice_diagnostic(
            "VOICE_AUDIO_CHUNK_RECEIVED",
            audio_base64="AAAA",
            embeddings=[0.1, 0.2],
            session_id="s1",
            size_bytes=4,
        )
    text = " ".join(r.message for r in caplog.records)
    assert "AAAA" not in text
    assert "0.1" not in text
    assert "embeddings" not in text.lower() or "embedding" not in text


def test_sanitize_strips_forbidden_keys() -> None:
    cleaned = sanitize_diagnostic_payload(
        {"audio_bytes": b"abc", "embedding": [1], "session_id": "x", "api_key": "secret"}
    )
    assert "audio_bytes" not in cleaned
    assert "embedding" not in cleaned
    assert "api_key" not in cleaned
    assert cleaned["session_id"] == "x"


def test_workspace_state_fields_update(
    orchestrator: LiveVoiceSessionOrchestrator, state_manager: StateManager
) -> None:
    sample = _enroll_user(orchestrator._speaker_identifier, "Nolan", 121)
    session = _start(orchestrator)
    sid = session["session_id"]
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(sample, "ok")
    orchestrator.submit_audio_chunk(sid, audio_bytes=sample, sequence=0)
    snap = state_manager.snapshot()
    assert snap.voice_session_state in {
        LiveSessionState.CAPTURING.value,
        LiveSessionState.SPEECH_DETECTED.value,
        LiveSessionState.LISTENING.value,
    }
    assert snap.voice_speech_detected is True
    orchestrator.finish_utterance(sid)
    snap2 = state_manager.snapshot()
    assert snap2.voice_session_state == LiveSessionState.LISTENING.value
    assert snap2.voice_current_speaker == "Nolan"
    assert snap2.voice_transcription_status == "completed"


def test_identity_confirm_and_reject(orchestrator: LiveVoiceSessionOrchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _start(orchestrator)
    sid = session["session_id"]
    audio = _speech_like(130, 1.2)

    def fake_identify(_audio: bytes):
        return SimpleNamespace(
            identity=SpeakerIdentity.UNKNOWN,
            confidence=0.60,
            requires_confirmation=True,
            reason="medium_confidence",
            matched_user="Nolan",
            recognition_band=RecognitionBand.MEDIUM,
            is_known=False,
            threshold=0.72,
        )

    monkeypatch.setattr(orchestrator._speaker_identifier, "identify", fake_identify)
    stt = orchestrator._stt_registry.get("mock")
    assert isinstance(stt, MockSpeechToTextProvider)
    stt.set_response(audio, "test")
    orchestrator.submit_audio_chunk(sid, audio_bytes=audio, sequence=0)
    orchestrator.finish_utterance(sid)
    confirmed = orchestrator.confirm_identity(sid, user="Nolan")
    assert confirmed["voice_current_speaker"] == "Nolan"

    # Reject path on a fresh medium match
    session2 = orchestrator.start_session(authenticated_user="Nolan")
    sid2 = session2["session_id"]
    audio2 = _speech_like(131, 1.2)
    stt.set_response(audio2, "test2")
    orchestrator.submit_audio_chunk(sid2, audio_bytes=audio2, sequence=0)
    orchestrator.finish_utterance(sid2)
    rejected = orchestrator.reject_identity(sid2)
    assert rejected["voice_current_speaker"] is None
    call_text = orchestrator._brain.process_request.call_args[0][0]
    assert RESTRICTED_UNKNOWN_PREFIX in call_text


# --- API auth -----------------------------------------------------------------


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "phase20-3-test-secret"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def voice_api_client(web_secret: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_titan()
    reset_live_orchestrator_for_tests()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    titan.brain.process_request = MagicMock(
        return_value=SimpleNamespace(final_response="ok")
    )
    set_titan(titan)

    with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
        "config.settings.get_web_secret_key", return_value=web_secret
    ), patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ), patch(
        "api.auth.is_session_auth_enabled", return_value=False
    ), patch(
        "api.auth_middleware.is_session_auth_enabled", return_value=False
    ), patch(
        "api.voice_session_routes.is_session_auth_enabled", return_value=False
    ):
        client = TestClient(create_app())
        yield client

    reset_live_orchestrator_for_tests()
    reset_titan()


def test_authenticated_user_can_start_voice_session(
    voice_api_client: TestClient, web_secret: str
) -> None:
    response = voice_api_client.post(
        "/voice/session/start",
        json={"capture_mode": "push_to_talk"},
        headers={"Authorization": f"Bearer {web_secret}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"]
    assert data["voice_session_state"] == LiveSessionState.LISTENING.value


def test_unauthenticated_user_rejected(voice_api_client: TestClient) -> None:
    response = voice_api_client.post(
        "/voice/session/start",
        json={"capture_mode": "push_to_talk"},
    )
    assert response.status_code == 401


def test_api_rejects_malformed_chunk(
    voice_api_client: TestClient, web_secret: str
) -> None:
    headers = {"Authorization": f"Bearer {web_secret}"}
    started = voice_api_client.post(
        "/voice/session/start", json={}, headers=headers
    ).json()
    sid = started["session_id"]
    bad = base64.b64encode(b"RIFF" + b"\x00" * 20).decode("ascii")
    response = voice_api_client.post(
        "/voice/session/chunk",
        json={"session_id": sid, "audio_base64": bad, "sequence": 0},
        headers=headers,
    )
    assert response.status_code == 400

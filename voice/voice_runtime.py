# =====================================
# Titan Voice Runtime
# =====================================

"""Real-time voice conversation runtime — external interface to Brain.process_request().

Voice Runtime never bypasses the Brain. It captures speech, transcribes, delegates
to ``Brain.process_request()``, synthesizes the response, and plays audio.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from config import settings as app_settings
from voice.audio_devices import (
    AudioCapture,
    AudioDeviceManager,
    AudioPlayback,
    MockAudioCapture,
    MockAudioPlayback,
)
from voice.exceptions import VoiceConfigurationError, VoiceInterruptedError, VoiceStateError
from voice.models import (
    ConversationMode,
    ConversationTurn,
    LatencyMetrics,
    VoiceConfig,
    VoiceSession,
    VoiceState,
    VoiceTurnResult,
)
from voice.speech_to_text import SpeechToTextRegistry, get_stt_registry, transcribe_audio
from voice.text_to_speech import TextToSpeechRegistry, get_tts_registry, synthesize_speech
from voice.voice_session import VoiceSessionStore

if TYPE_CHECKING:
    from brain.brain import Brain

logger = logging.getLogger(__name__)


def voice_config_from_settings() -> VoiceConfig:
    """Build ``VoiceConfig`` from ``config.settings`` environment values."""
    mode_raw = app_settings.TITAN_VOICE_CONVERSATION_MODE.strip().lower()
    try:
        mode = ConversationMode(mode_raw)
    except ValueError:
        mode = ConversationMode.SINGLE_SHOT
    return VoiceConfig(
        language=app_settings.TITAN_VOICE_LOCALE,
        voice=app_settings.TITAN_VOICE_VOICE,
        speed=app_settings.TITAN_VOICE_TTS_RATE,
        volume=app_settings.TITAN_VOICE_VOLUME,
        stt_provider=app_settings.TITAN_VOICE_STT_PROVIDER,
        tts_provider=app_settings.TITAN_VOICE_TTS_PROVIDER,
        microphone_device=app_settings.TITAN_VOICE_MICROPHONE,
        speaker_device=app_settings.TITAN_VOICE_SPEAKER,
        silence_timeout_seconds=app_settings.TITAN_VOICE_SILENCE_TIMEOUT,
        conversation_mode=mode,
    )


class VoiceRuntime:
    """Provider-agnostic voice interface — always routes through Brain.process_request()."""

    _VALID_TRANSITIONS: dict[VoiceState, frozenset[VoiceState]] = {
        VoiceState.IDLE: frozenset({VoiceState.LISTENING, VoiceState.THINKING, VoiceState.PAUSED, VoiceState.ERROR}),
        VoiceState.LISTENING: frozenset({VoiceState.THINKING, VoiceState.IDLE, VoiceState.PAUSED, VoiceState.ERROR}),
        VoiceState.THINKING: frozenset({VoiceState.SPEAKING, VoiceState.IDLE, VoiceState.ERROR}),
        VoiceState.SPEAKING: frozenset({VoiceState.IDLE, VoiceState.LISTENING, VoiceState.PAUSED, VoiceState.ERROR}),
        VoiceState.PAUSED: frozenset({VoiceState.IDLE, VoiceState.LISTENING, VoiceState.ERROR}),
        VoiceState.ERROR: frozenset({VoiceState.IDLE}),
    }

    def __init__(
        self,
        brain: Brain,
        *,
        config: VoiceConfig | None = None,
        session_store: VoiceSessionStore | None = None,
        stt_registry: SpeechToTextRegistry | None = None,
        tts_registry: TextToSpeechRegistry | None = None,
        device_manager: AudioDeviceManager | None = None,
        audio_capture: AudioCapture | None = None,
        audio_playback: AudioPlayback | None = None,
    ) -> None:
        self._brain = brain
        self._config = config or voice_config_from_settings()
        self._session_store = session_store or VoiceSessionStore()
        self._stt_registry = stt_registry or get_stt_registry()
        self._tts_registry = tts_registry or get_tts_registry()
        self._device_manager = device_manager or AudioDeviceManager()
        self._capture = audio_capture or MockAudioCapture()
        self._playback = audio_playback or MockAudioPlayback()
        self._session: VoiceSession | None = None
        self._state = VoiceState.IDLE
        self._interrupt_requested = False
        self._speaking_cancelled = False
        self._response_queue: deque[str] = deque()

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def config(self) -> VoiceConfig:
        return self._config

    @property
    def session(self) -> VoiceSession | None:
        return self._session

    def start_session(
        self,
        *,
        config: VoiceConfig | None = None,
        conversation_id: str | None = None,
        resume: bool = False,
    ) -> VoiceSession:
        """Create or resume a persistent voice session."""
        if config is not None:
            self._config = config
        if resume:
            existing = self._session_store.get_active_session()
            if existing is not None and existing.active:
                self._session = existing
                self._set_state(VoiceState.IDLE)
                logger.info("Voice session resumed id=%s", existing.conversation_id)
                return existing
        self._session = self._session_store.create_session(
            config=self._config,
            conversation_id=conversation_id,
        )
        self._set_state(VoiceState.IDLE)
        return self._session

    def end_session(self) -> VoiceSession | None:
        """End the active voice session."""
        if self._session is None:
            return None
        self.stop_playback()
        ended = self._session_store.end_session(self._session.conversation_id)
        self._session = None
        self._set_state(VoiceState.IDLE)
        return ended

    def pause(self) -> None:
        """Pause listening and speaking."""
        if self._state not in {VoiceState.LISTENING, VoiceState.SPEAKING}:
            raise VoiceStateError(f"Cannot pause from state {self._state.value}")
        self.interrupt_speaking()
        if self._capture.is_listening():
            self._capture.stop_listening()
        self._set_state(VoiceState.PAUSED)

    def resume(self) -> None:
        """Resume from paused state."""
        if self._state != VoiceState.PAUSED:
            raise VoiceStateError(f"Cannot resume from state {self._state.value}")
        self._set_state(VoiceState.IDLE)

    def process_text_turn(self, text: str) -> VoiceTurnResult:
        """Process a text utterance (test path / push-to-talk transcript)."""
        self._ensure_session()
        request = (text or "").strip()
        if not request:
            raise VoiceConfigurationError("Empty utterance — nothing to process")

        metrics = LatencyMetrics()
        turn_started = time.perf_counter()

        self._set_state(VoiceState.THINKING)
        brain_started = time.perf_counter()
        result = self._brain.process_request(request)
        metrics.brain_seconds = time.perf_counter() - brain_started
        response_text = (result.final_response or "").strip()

        interrupted = self._consume_interrupt()
        if interrupted:
            self._queue_response(response_text)
            return self._build_turn_result(request, response_text, metrics, turn_started, interrupted=True)

        self._set_state(VoiceState.SPEAKING)
        tts_started = time.perf_counter()
        synthesis = synthesize_speech(
            response_text,
            locale=self._config.language,
            voice=self._config.voice,
            speed=self._config.speed,
            volume=self._config.volume,
            provider_id=self._config.tts_provider,
            registry=self._tts_registry,
        )
        metrics.tts_seconds = time.perf_counter() - tts_started

        if not self._speaking_cancelled:
            self._playback.play(
                synthesis.audio_bytes,
                device_id=self._config.speaker_device,
                volume=self._config.volume,
            )
        else:
            interrupted = True
            self._speaking_cancelled = False

        metrics.total_seconds = time.perf_counter() - turn_started
        self._record_turn(request, response_text, metrics)
        self._set_state(VoiceState.IDLE)
        self._log_turn_metrics(request, metrics)
        return self._build_turn_result(request, response_text, metrics, turn_started, interrupted=interrupted)

    def process_audio_turn(self, audio_bytes: bytes) -> VoiceTurnResult:
        """Full STT → Brain → TTS pipeline for raw audio."""
        self._ensure_session()
        metrics = LatencyMetrics()
        turn_started = time.perf_counter()
        metrics.speech_start = datetime.now(timezone.utc)

        self._set_state(VoiceState.LISTENING)
        stt_started = time.perf_counter()
        transcription = transcribe_audio(
            audio_bytes,
            locale=self._config.language,
            provider_id=self._config.stt_provider,
            registry=self._stt_registry,
        )
        metrics.transcription_seconds = time.perf_counter() - stt_started
        metrics.speech_end = datetime.now(timezone.utc)

        logger.info(
            "Speech transcribed provider=%s duration=%.4fs chars=%d",
            transcription.provider_id,
            metrics.transcription_seconds,
            len(transcription.text),
        )

        turn_result = self.process_text_turn(transcription.text)
        turn_result.metrics.speech_start = metrics.speech_start
        turn_result.metrics.speech_end = metrics.speech_end
        turn_result.metrics.transcription_seconds = metrics.transcription_seconds
        turn_result.metrics.total_seconds = time.perf_counter() - turn_started
        return turn_result

    def listen_once(self) -> VoiceTurnResult:
        """Single-shot: capture one utterance then process."""
        self._ensure_session()
        self._device_manager.resolve_input(self._config.microphone_device)
        self._set_state(VoiceState.LISTENING)
        self._capture.start_listening(
            device_id=self._config.microphone_device,
            silence_timeout=self._config.silence_timeout_seconds,
        )
        audio = self._capture.stop_listening()
        return self.process_audio_turn(audio)

    def listen_continuous(self, max_turns: int = 1) -> list[VoiceTurnResult]:
        """Continuous conversation — process up to *max_turns* utterances."""
        self._config = VoiceConfig.from_dict({
            **self._config.to_dict(),
            "conversation_mode": ConversationMode.CONTINUOUS.value,
        })
        results: list[VoiceTurnResult] = []
        for _ in range(max(1, max_turns)):
            if self._interrupt_requested:
                break
            results.append(self.listen_once())
        return results

    def push_to_talk_start(self) -> None:
        """Begin push-to-talk capture."""
        self._ensure_session()
        self._config = VoiceConfig.from_dict({
            **self._config.to_dict(),
            "conversation_mode": ConversationMode.PUSH_TO_TALK.value,
        })
        self._device_manager.resolve_input(self._config.microphone_device)
        self._set_state(VoiceState.LISTENING)
        self._capture.start_listening(
            device_id=self._config.microphone_device,
            silence_timeout=self._config.silence_timeout_seconds,
        )

    def push_to_talk_stop(self) -> VoiceTurnResult:
        """End push-to-talk capture and process the utterance."""
        if self._state != VoiceState.LISTENING:
            raise VoiceStateError("push_to_talk_stop requires LISTENING state")
        audio = self._capture.stop_listening()
        return self.process_audio_turn(audio)

    def interrupt_speaking(self) -> None:
        """Cancel current speech synthesis/playback."""
        self._speaking_cancelled = True
        self._interrupt_requested = True
        self._playback.stop()
        logger.info("Voice interruption requested")

    def cancel_current_speech(self) -> None:
        """Alias for interrupt_speaking — stops TTS and clears speaking state."""
        self.interrupt_speaking()

    def stop_playback(self) -> None:
        """Stop audio playback immediately."""
        self._playback.stop()

    def queue_response(self, text: str) -> None:
        """Queue a response for playback after current speech is cancelled."""
        self._queue_response(text)

    def flush_response_queue(self) -> list[VoiceTurnResult]:
        """Speak all queued responses."""
        results: list[VoiceTurnResult] = []
        while self._response_queue:
            text = self._response_queue.popleft()
            results.append(self.process_text_turn(text))
        return results

    def get_status(self) -> dict[str, Any]:
        """Runtime status for API / diagnostics."""
        session = self._session
        return {
            "enabled": app_settings.TITAN_VOICE_ENABLED,
            "state": self._state.value,
            "config": self._config.to_dict(),
            "session": session.to_dict() if session else None,
            "stt_providers": self._stt_registry.list_providers(),
            "tts_providers": self._tts_registry.list_providers(),
            "input_devices": [d.to_dict() for d in self._device_manager.list_input_devices()],
            "output_devices": [d.to_dict() for d in self._device_manager.list_output_devices()],
            "queue_depth": len(self._response_queue),
            "interrupt_requested": self._interrupt_requested,
        }

    def _ensure_session(self) -> VoiceSession:
        if self._session is None or not self._session.active:
            self.start_session()
        assert self._session is not None
        return self._session

    def _set_state(self, new_state: VoiceState) -> None:
        allowed = self._VALID_TRANSITIONS.get(self._state, frozenset())
        if new_state != self._state and new_state not in allowed:
            raise VoiceStateError(
                f"Invalid voice state transition {self._state.value} → {new_state.value}"
            )
        old = self._state
        self._state = new_state
        if self._session is not None:
            self._session.state = new_state
            self._session_store.update_session(self._session)
        logger.debug("Voice state %s → %s", old.value, new_state.value)

    def _record_turn(self, user_text: str, assistant_text: str, metrics: LatencyMetrics) -> None:
        if self._session is None:
            return
        turn = ConversationTurn(
            user_text=user_text,
            assistant_text=assistant_text,
            brain_duration_seconds=metrics.brain_seconds,
            stt_duration_seconds=metrics.transcription_seconds,
            tts_duration_seconds=metrics.tts_seconds,
            total_latency_seconds=metrics.total_seconds,
        )
        self._session.add_turn(turn)
        self._session_store.update_session(self._session)

    def _build_turn_result(
        self,
        user_text: str,
        assistant_text: str,
        metrics: LatencyMetrics,
        turn_started: float,
        *,
        interrupted: bool,
    ) -> VoiceTurnResult:
        if metrics.total_seconds <= 0:
            metrics.total_seconds = time.perf_counter() - turn_started
        session_id = self._session.conversation_id if self._session else ""
        return VoiceTurnResult(
            session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
            state=self._state,
            metrics=metrics,
            interrupted=interrupted,
        )

    def _queue_response(self, text: str) -> None:
        cleaned = (text or "").strip()
        if cleaned:
            self._response_queue.append(cleaned)

    def _consume_interrupt(self) -> bool:
        was_set = self._interrupt_requested
        self._interrupt_requested = False
        return was_set

    def _log_turn_metrics(self, request: str, metrics: LatencyMetrics) -> None:
        safe_preview = request[:80] + ("…" if len(request) > 80 else "")
        logger.info(
            "Voice turn complete request=%r stt=%.4fs brain=%.4fs tts=%.4fs total=%.4fs",
            safe_preview,
            metrics.transcription_seconds,
            metrics.brain_seconds,
            metrics.tts_seconds,
            metrics.total_seconds,
        )

# =====================================
# Titan Voice Manager
# =====================================

"""Provider-independent voice orchestration facade (Phase 17.8).

The web interface performs browser STT/TTS in V1. This module exposes
configuration, capability discovery, and future server-side provider hooks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from config import settings as app_settings


@dataclass(frozen=True)
class VoiceCapabilities:
    """Runtime voice feature flags exposed to clients."""

    enabled: bool
    push_to_talk: bool
    continuous_listening: bool
    wake_word: bool
    interrupt_on_listen: bool
    stt_provider: str
    tts_provider: str
    locale: str
    tts_rate: float
    tts_pitch: float
    speaker_identification: bool
    live_stt_providers: tuple[str, ...]
    live_tts_providers: tuple[str, ...]


class SpeechToTextProvider(Protocol):
    """Future server-side STT provider contract."""

    def transcribe(self, audio_bytes: bytes, *, locale: str) -> str:
        """Return transcript text from raw audio."""
        ...


class TextToSpeechProvider(Protocol):
    """Future server-side TTS provider contract."""

    def synthesize(self, text: str, *, locale: str) -> bytes:
        """Return encoded audio bytes for playback."""
        ...


class VoiceManager:
    """Voice configuration and future provider registry."""

    def __init__(
        self,
        *,
        stt_provider: SpeechToTextProvider | None = None,
        tts_provider: TextToSpeechProvider | None = None,
    ) -> None:
        self._stt = stt_provider
        self._tts = tts_provider

    def get_capabilities(self) -> VoiceCapabilities:
        """Return voice capabilities for the active deployment."""
        return VoiceCapabilities(
            enabled=app_settings.TITAN_VOICE_ENABLED,
            push_to_talk=True,
            continuous_listening=app_settings.TITAN_VOICE_CONTINUOUS,
            wake_word=False,
            interrupt_on_listen=True,
            stt_provider=self._resolve_stt_provider(),
            tts_provider=self._resolve_tts_provider(),
            locale=app_settings.TITAN_VOICE_LOCALE,
            tts_rate=app_settings.TITAN_VOICE_TTS_RATE,
            tts_pitch=app_settings.TITAN_VOICE_TTS_PITCH,
            speaker_identification=app_settings.TITAN_VOICE_SPEAKER_ID_ENABLED,
            live_stt_providers=("mock", "openai_whisper"),
            live_tts_providers=("mock", "openai_tts"),
        )

    def get_config(self) -> dict[str, Any]:
        """Serialize voice configuration for API consumers."""
        caps = self.get_capabilities()
        return {
            "capabilities": asdict(caps),
            "modes": {
                "push_to_talk": caps.push_to_talk,
                "continuous": caps.continuous_listening,
                "wake_word": caps.wake_word,
            },
            "providers": {
                "stt": caps.stt_provider,
                "tts": caps.tts_provider,
                "configured_stt": app_settings.TITAN_VOICE_STT_PROVIDER,
                "configured_tts": app_settings.TITAN_VOICE_TTS_PROVIDER,
            },
            "speech": {
                "locale": caps.locale,
                "rate": caps.tts_rate,
                "pitch": caps.tts_pitch,
            },
            "speaker_identification": {
                "enabled": caps.speaker_identification,
                "min_confidence": app_settings.TITAN_VOICE_SPEAKER_MIN_CONFIDENCE,
                "medium_confidence": app_settings.TITAN_VOICE_SPEAKER_MEDIUM_CONFIDENCE,
                "ambiguity_delta": app_settings.TITAN_VOICE_SPEAKER_AMBIGUITY_DELTA,
            },
            "enrollment": {
                "min_samples": app_settings.TITAN_VOICE_ENROLLMENT_MIN_SAMPLES,
                "max_samples": app_settings.TITAN_VOICE_ENROLLMENT_MAX_SAMPLES,
                "min_duration_seconds": app_settings.TITAN_VOICE_ENROLLMENT_MIN_DURATION,
                "max_duration_seconds": app_settings.TITAN_VOICE_ENROLLMENT_MAX_DURATION,
                "min_quality": app_settings.TITAN_VOICE_ENROLLMENT_MIN_QUALITY,
                "min_confidence": app_settings.TITAN_VOICE_ENROLLMENT_MIN_CONFIDENCE,
            },
            "live_session": {
                "always_listening": False,
                "wake_word_enabled": bool(
                    getattr(app_settings, "TITAN_VOICE_WAKE_WORD_ENABLED", False)
                ),
                "capture_modes": ["push_to_talk", "single_shot", "wake_word"],
                "tts_strategy": getattr(
                    app_settings, "TITAN_VOICE_TTS_STRATEGY", "sentence_buffered"
                ),
                "vad": {
                    "speech_start_threshold": getattr(
                        app_settings, "TITAN_VOICE_VAD_SPEECH_START", 0.035
                    ),
                    "speech_end_threshold": getattr(
                        app_settings, "TITAN_VOICE_VAD_SPEECH_END", 0.018
                    ),
                    "silence_timeout_seconds": getattr(
                        app_settings, "TITAN_VOICE_VAD_SILENCE_TIMEOUT", 1.2
                    ),
                    "min_utterance_duration_seconds": getattr(
                        app_settings, "TITAN_VOICE_VAD_MIN_UTTERANCE", 0.35
                    ),
                    "max_utterance_duration_seconds": getattr(
                        app_settings, "TITAN_VOICE_VAD_MAX_UTTERANCE", 30.0
                    ),
                    "sensitivity": getattr(
                        app_settings, "TITAN_VOICE_VAD_SENSITIVITY", 0.55
                    ),
                },
                "identity_confirm_timeout_seconds": getattr(
                    app_settings, "TITAN_VOICE_IDENTITY_CONFIRM_TIMEOUT", 45.0
                ),
            },
        }

    def _resolve_stt_provider(self) -> str:
        if self._stt is not None:
            return type(self._stt).__name__
        configured = app_settings.TITAN_VOICE_STT_PROVIDER
        if configured and configured != "mock":
            return configured
        return "browser_webspeech"

    def _resolve_tts_provider(self) -> str:
        if self._tts is not None:
            return type(self._tts).__name__
        configured = app_settings.TITAN_VOICE_TTS_PROVIDER
        if configured and configured != "mock":
            return configured
        return "browser_speech_synthesis"

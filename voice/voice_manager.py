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
            },
            "speech": {
                "locale": caps.locale,
                "rate": caps.tts_rate,
                "pitch": caps.tts_pitch,
            },
        }

    def _resolve_stt_provider(self) -> str:
        if self._stt is not None:
            return type(self._stt).__name__
        return "browser_webspeech"

    def _resolve_tts_provider(self) -> str:
        if self._tts is not None:
            return type(self._tts).__name__
        return "browser_speech_synthesis"

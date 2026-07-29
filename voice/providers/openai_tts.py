# =====================================
# Titan OpenAI TTS Provider
# =====================================

"""OpenAI text-to-speech adapter (Phase 20.1)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from voice.exceptions import VoiceConfigurationError, VoiceProviderError
from voice.text_to_speech import SynthesisResult, TextToSpeechProvider

logger = logging.getLogger(__name__)

_DEFAULT_VOICE = "alloy"
_VOICE_ALIASES = {
    "default": _DEFAULT_VOICE,
    "alloy": "alloy",
    "echo": "echo",
    "fable": "fable",
    "onyx": "onyx",
    "nova": "nova",
    "shimmer": "shimmer",
}


class OpenAITextToSpeechProvider(TextToSpeechProvider):
    """Synthesize speech via OpenAI Audio Speech API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini-tts",
        client: Any | None = None,
    ) -> None:
        self._api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self._model = (model or "gpt-4o-mini-tts").strip()
        self._client = client

    @property
    def provider_id(self) -> str:
        return "openai_tts"

    def health_check(self) -> bool:
        return bool(self._api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise VoiceConfigurationError(
                "OpenAI TTS requires OPENAI_API_KEY or an injected client"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise VoiceConfigurationError(
                "openai package is required for openai_tts"
            ) from exc
        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def synthesize(
        self,
        text: str,
        *,
        locale: str,
        voice: str = "default",
        speed: float = 1.0,
        volume: float = 1.0,
        **kwargs: Any,
    ) -> SynthesisResult:
        _ = volume  # Playback volume is applied by AudioPlayback, not the provider.
        cleaned = (text or "").strip()
        if not cleaned:
            raise VoiceProviderError("Cannot synthesize empty text")
        started = time.perf_counter()
        client = self._get_client()
        voice_id = _resolve_voice(voice)
        clamped_speed = max(0.25, min(4.0, float(speed)))
        try:
            response = client.audio.speech.create(
                model=self._model,
                voice=voice_id,
                input=cleaned,
                speed=clamped_speed,
            )
            audio_bytes = _extract_audio_bytes(response)
        except VoiceConfigurationError:
            raise
        except Exception as exc:
            logger.exception("OpenAI TTS synthesis failed")
            raise VoiceProviderError(f"OpenAI TTS failed: {exc}") from exc

        duration = time.perf_counter() - started
        logger.info(
            "TTS_OPENAI locale=%s voice=%s chars=%d duration=%.4fs",
            locale,
            voice_id,
            len(cleaned),
            duration,
        )
        return SynthesisResult(
            audio_bytes=audio_bytes,
            duration_seconds=duration,
            provider_id=self.provider_id,
            locale=locale,
            voice=voice_id,
        )


def _resolve_voice(voice: str) -> str:
    key = (voice or "default").strip().lower()
    return _VOICE_ALIASES.get(key, key or _DEFAULT_VOICE)


def _extract_audio_bytes(response: Any) -> bytes:
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)
    if hasattr(response, "content") and isinstance(response.content, (bytes, bytearray)):
        return bytes(response.content)
    if hasattr(response, "read"):
        payload = response.read()
        return bytes(payload)
    raise VoiceProviderError("OpenAI TTS returned unsupported audio payload")

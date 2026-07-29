# =====================================
# Titan OpenAI Whisper STT Provider
# =====================================

"""OpenAI Whisper speech-to-text adapter (Phase 20.1)."""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Any

from voice.exceptions import VoiceConfigurationError, VoiceProviderError
from voice.speech_to_text import SpeechToTextProvider, TranscriptionResult

logger = logging.getLogger(__name__)


class OpenAIWhisperSpeechToTextProvider(SpeechToTextProvider):
    """Transcribe audio via OpenAI Audio Transcriptions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "whisper-1",
        client: Any | None = None,
    ) -> None:
        self._api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self._model = (model or "whisper-1").strip()
        self._client = client

    @property
    def provider_id(self) -> str:
        return "openai_whisper"

    def health_check(self) -> bool:
        return bool(self._api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise VoiceConfigurationError(
                "OpenAI Whisper STT requires OPENAI_API_KEY or an injected client"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise VoiceConfigurationError(
                "openai package is required for openai_whisper STT"
            ) from exc
        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        locale: str,
        **kwargs: Any,
    ) -> TranscriptionResult:
        if not audio_bytes:
            raise VoiceProviderError("Cannot transcribe empty audio")
        started = time.perf_counter()
        client = self._get_client()
        language = _locale_to_language(locale)
        filename = str(kwargs.get("filename") or "speech.wav")
        try:
            buffer = io.BytesIO(audio_bytes)
            buffer.name = filename  # type: ignore[attr-defined]
            response = client.audio.transcriptions.create(
                model=self._model,
                file=buffer,
                language=language,
            )
        except VoiceConfigurationError:
            raise
        except Exception as exc:
            logger.exception("OpenAI Whisper transcription failed")
            raise VoiceProviderError(f"OpenAI Whisper STT failed: {exc}") from exc

        text = str(getattr(response, "text", "") or "").strip()
        duration = time.perf_counter() - started
        logger.info(
            "STT_OPENAI_WHISPER locale=%s chars=%d duration=%.4fs",
            locale,
            len(text),
            duration,
        )
        return TranscriptionResult(
            text=text,
            duration_seconds=duration,
            provider_id=self.provider_id,
            locale=locale,
            confidence=None,
        )


def _locale_to_language(locale: str) -> str | None:
    cleaned = (locale or "").strip()
    if not cleaned:
        return None
    return cleaned.split("-", 1)[0].lower()

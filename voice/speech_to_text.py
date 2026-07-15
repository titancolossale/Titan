# =====================================
# Titan Speech-To-Text
# =====================================

"""Provider-agnostic speech-to-text abstraction for Voice Runtime V1."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from voice.exceptions import VoiceConfigurationError, VoiceProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptionResult:
    """STT output with timing metadata."""

    text: str
    duration_seconds: float
    provider_id: str
    locale: str
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "duration_seconds": round(self.duration_seconds, 4),
            "provider_id": self.provider_id,
            "locale": self.locale,
            "confidence": self.confidence,
        }


class SpeechToTextProvider(ABC):
    """Abstract STT provider — swap without changing Voice Runtime."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier (e.g. openai_whisper, deepgram)."""

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        locale: str,
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Convert raw audio bytes to transcript text."""

    def health_check(self) -> bool:
        """Return True when the provider is configured and reachable."""
        return True


class MockSpeechToTextProvider(SpeechToTextProvider):
    """Deterministic STT for tests and offline development."""

    def __init__(self, *, default_text: str = "bonjour titan") -> None:
        self._default_text = default_text
        self._responses: dict[bytes, str] = {}

    @property
    def provider_id(self) -> str:
        return "mock"

    def set_response(self, audio_bytes: bytes, text: str) -> None:
        """Map specific audio input to transcript (test helper)."""
        self._responses[audio_bytes] = text

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        locale: str,
        **kwargs: Any,
    ) -> TranscriptionResult:
        started = time.perf_counter()
        text = self._responses.get(audio_bytes, self._default_text)
        duration = time.perf_counter() - started
        logger.debug("Mock STT locale=%s text=%r duration=%.4fs", locale, text, duration)
        return TranscriptionResult(
            text=text,
            duration_seconds=duration,
            provider_id=self.provider_id,
            locale=locale,
            confidence=1.0,
        )


class SpeechToTextRegistry:
    """Registry and factory for STT providers."""

    def __init__(self) -> None:
        self._providers: dict[str, SpeechToTextProvider] = {}
        self.register(MockSpeechToTextProvider())

    def register(self, provider: SpeechToTextProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> SpeechToTextProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise VoiceConfigurationError(
                f"Unknown STT provider {provider_id!r}. "
                f"Registered: {sorted(self._providers)}"
            )
        return provider

    def list_providers(self) -> list[str]:
        return sorted(self._providers)

    def resolve(self, provider_id: str | None) -> SpeechToTextProvider:
        key = (provider_id or "mock").strip().lower()
        return self.get(key)


_DEFAULT_STT_REGISTRY = SpeechToTextRegistry()


def get_stt_registry() -> SpeechToTextRegistry:
    """Return the process-wide STT provider registry."""
    return _DEFAULT_STT_REGISTRY


def transcribe_audio(
    audio_bytes: bytes,
    *,
    locale: str,
    provider_id: str = "mock",
    registry: SpeechToTextRegistry | None = None,
    **kwargs: Any,
) -> TranscriptionResult:
    """Transcribe audio using the configured provider."""
    reg = registry or get_stt_registry()
    provider = reg.resolve(provider_id)
    try:
        return provider.transcribe(audio_bytes, locale=locale, **kwargs)
    except VoiceProviderError:
        raise
    except Exception as exc:
        logger.exception("STT provider %s failed", provider.provider_id)
        raise VoiceProviderError(f"STT transcription failed: {exc}") from exc

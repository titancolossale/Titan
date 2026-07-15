# =====================================
# Titan Text-To-Speech
# =====================================

"""Provider-agnostic text-to-speech abstraction for Voice Runtime V1."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from voice.exceptions import VoiceConfigurationError, VoiceProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynthesisResult:
    """TTS output with timing metadata."""

    audio_bytes: bytes
    duration_seconds: float
    provider_id: str
    locale: str
    voice: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_size_bytes": len(self.audio_bytes),
            "duration_seconds": round(self.duration_seconds, 4),
            "provider_id": self.provider_id,
            "locale": self.locale,
            "voice": self.voice,
        }


class TextToSpeechProvider(ABC):
    """Abstract TTS provider — swap without changing Voice Runtime."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier (e.g. openai, elevenlabs, piper)."""

    @abstractmethod
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
        """Convert text to encoded audio bytes."""

    def health_check(self) -> bool:
        """Return True when the provider is configured and reachable."""
        return True


class MockTextToSpeechProvider(TextToSpeechProvider):
    """Deterministic TTS for tests and offline development."""

    @property
    def provider_id(self) -> str:
        return "mock"

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
        started = time.perf_counter()
        # Encode text length as pseudo-audio for test assertions (no secrets).
        payload = f"mock-audio:{locale}:{voice}:{len(text)}".encode("utf-8")
        duration = time.perf_counter() - started
        logger.debug(
            "Mock TTS locale=%s voice=%s chars=%d duration=%.4fs",
            locale,
            voice,
            len(text),
            duration,
        )
        return SynthesisResult(
            audio_bytes=payload,
            duration_seconds=duration,
            provider_id=self.provider_id,
            locale=locale,
            voice=voice,
        )


class TextToSpeechRegistry:
    """Registry and factory for TTS providers."""

    def __init__(self) -> None:
        self._providers: dict[str, TextToSpeechProvider] = {}
        self.register(MockTextToSpeechProvider())

    def register(self, provider: TextToSpeechProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> TextToSpeechProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise VoiceConfigurationError(
                f"Unknown TTS provider {provider_id!r}. "
                f"Registered: {sorted(self._providers)}"
            )
        return provider

    def list_providers(self) -> list[str]:
        return sorted(self._providers)

    def resolve(self, provider_id: str | None) -> TextToSpeechProvider:
        key = (provider_id or "mock").strip().lower()
        return self.get(key)


_DEFAULT_TTS_REGISTRY = TextToSpeechRegistry()


def get_tts_registry() -> TextToSpeechRegistry:
    """Return the process-wide TTS provider registry."""
    return _DEFAULT_TTS_REGISTRY


def synthesize_speech(
    text: str,
    *,
    locale: str,
    voice: str = "default",
    speed: float = 1.0,
    volume: float = 1.0,
    provider_id: str = "mock",
    registry: TextToSpeechRegistry | None = None,
    **kwargs: Any,
) -> SynthesisResult:
    """Synthesize speech using the configured provider."""
    reg = registry or get_tts_registry()
    provider = reg.resolve(provider_id)
    try:
        return provider.synthesize(
            text,
            locale=locale,
            voice=voice,
            speed=speed,
            volume=volume,
            **kwargs,
        )
    except VoiceProviderError:
        raise
    except Exception as exc:
        logger.exception("TTS provider %s failed", provider.provider_id)
        raise VoiceProviderError(f"TTS synthesis failed: {exc}") from exc

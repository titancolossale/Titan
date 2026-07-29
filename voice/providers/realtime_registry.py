# =====================================
# Titan Realtime Provider Registry
# =====================================

"""Configurable selection + listing of realtime streaming providers (Phase 20.6)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from voice.exceptions import VoiceConfigurationError
from voice.providers.realtime_stt import MockRealtimeSTTProvider, RealtimeSTTProvider
from voice.providers.realtime_tts import MockRealtimeTTSProvider, RealtimeTTSProvider
from voice.providers.streaming_models import StreamCapabilities

logger = logging.getLogger(__name__)

STTFactory = Callable[[], RealtimeSTTProvider]
TTSFactory = Callable[[], RealtimeTTSProvider]


class RealtimeProviderRegistry:
    """Registry for realtime STT/TTS providers — selection stays configurable."""

    def __init__(self) -> None:
        self._stt: dict[str, STTFactory] = {}
        self._tts: dict[str, TTSFactory] = {}
        self._stt_fallback: list[str] = []
        self._tts_fallback: list[str] = []
        self.register_stt("mock_realtime_stt", MockRealtimeSTTProvider)
        self.register_tts("mock_realtime_tts", MockRealtimeTTSProvider)

    def register_stt(self, provider_id: str, factory: STTFactory) -> None:
        key = provider_id.strip().lower()
        self._stt[key] = factory

    def register_tts(self, provider_id: str, factory: TTSFactory) -> None:
        key = provider_id.strip().lower()
        self._tts[key] = factory

    def set_stt_fallback_chain(self, provider_ids: list[str]) -> None:
        self._stt_fallback = [p.strip().lower() for p in provider_ids if p.strip()]

    def set_tts_fallback_chain(self, provider_ids: list[str]) -> None:
        self._tts_fallback = [p.strip().lower() for p in provider_ids if p.strip()]

    def list_stt(self) -> list[str]:
        return sorted(self._stt)

    def list_tts(self) -> list[str]:
        return sorted(self._tts)

    def stt_fallback_chain(self) -> list[str]:
        return list(self._stt_fallback)

    def tts_fallback_chain(self) -> list[str]:
        return list(self._tts_fallback)

    def create_stt(self, provider_id: str | None) -> RealtimeSTTProvider:
        key = (provider_id or "mock_realtime_stt").strip().lower()
        factory = self._stt.get(key)
        if factory is None:
            raise VoiceConfigurationError(
                f"Unknown realtime STT provider {key!r}. Registered: {self.list_stt()}"
            )
        return factory()

    def create_tts(self, provider_id: str | None) -> RealtimeTTSProvider:
        key = (provider_id or "mock_realtime_tts").strip().lower()
        factory = self._tts.get(key)
        if factory is None:
            raise VoiceConfigurationError(
                f"Unknown realtime TTS provider {key!r}. Registered: {self.list_tts()}"
            )
        return factory()

    def resolve_stt_with_fallback(
        self, preferred: str | None
    ) -> tuple[RealtimeSTTProvider, list[str]]:
        """Create preferred STT; return provider + remaining fallback ids."""
        preferred_key = (preferred or "mock_realtime_stt").strip().lower()
        chain = [preferred_key]
        for item in self._stt_fallback:
            if item not in chain:
                chain.append(item)
        if "mock_realtime_stt" not in chain:
            chain.append("mock_realtime_stt")
        last_exc: Exception | None = None
        for idx, provider_id in enumerate(chain):
            if provider_id not in self._stt:
                continue
            try:
                provider = self.create_stt(provider_id)
                if provider.health_check():
                    return provider, chain[idx + 1 :]
            except Exception as exc:
                last_exc = exc
                logger.warning("Realtime STT %s unavailable: %s", provider_id, exc)
        raise VoiceConfigurationError(
            f"No healthy realtime STT provider in chain {chain}: {last_exc}"
        )

    def resolve_tts_with_fallback(
        self, preferred: str | None
    ) -> tuple[RealtimeTTSProvider, list[str]]:
        preferred_key = (preferred or "mock_realtime_tts").strip().lower()
        chain = [preferred_key]
        for item in self._tts_fallback:
            if item not in chain:
                chain.append(item)
        if "mock_realtime_tts" not in chain:
            chain.append("mock_realtime_tts")
        last_exc: Exception | None = None
        for idx, provider_id in enumerate(chain):
            if provider_id not in self._tts:
                continue
            try:
                provider = self.create_tts(provider_id)
                if provider.health_check():
                    return provider, chain[idx + 1 :]
            except Exception as exc:
                last_exc = exc
                logger.warning("Realtime TTS %s unavailable: %s", provider_id, exc)
        raise VoiceConfigurationError(
            f"No healthy realtime TTS provider in chain {chain}: {last_exc}"
        )

    def capabilities_snapshot(self) -> dict[str, Any]:
        stt_caps: list[dict[str, Any]] = []
        tts_caps: list[dict[str, Any]] = []
        for provider_id in self.list_stt():
            try:
                caps = self.create_stt(provider_id).capabilities
                stt_caps.append(caps.to_dict() if isinstance(caps, StreamCapabilities) else {})
            except Exception:
                stt_caps.append({"provider_id": provider_id, "error": "init_failed"})
        for provider_id in self.list_tts():
            try:
                caps = self.create_tts(provider_id).capabilities
                tts_caps.append(caps.to_dict() if isinstance(caps, StreamCapabilities) else {})
            except Exception:
                tts_caps.append({"provider_id": provider_id, "error": "init_failed"})
        return {
            "stt": stt_caps,
            "tts": tts_caps,
            "stt_fallback": self.stt_fallback_chain(),
            "tts_fallback": self.tts_fallback_chain(),
        }


_DEFAULT_REALTIME_REGISTRY = RealtimeProviderRegistry()


def get_realtime_registry() -> RealtimeProviderRegistry:
    return _DEFAULT_REALTIME_REGISTRY

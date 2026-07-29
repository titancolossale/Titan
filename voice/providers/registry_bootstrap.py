# =====================================
# Titan Voice Provider Registry Bootstrap
# =====================================

"""Register live + realtime voice providers onto process-wide registries (Phase 20.1/20.6/20.8)."""

from __future__ import annotations

import logging
import os
from typing import Any

from config import settings as app_settings
from voice.providers.deepgram_streaming import DeepgramStreamingSTT
from voice.providers.elevenlabs_streaming import ElevenLabsStreamingTTS
from voice.providers.openai_realtime import OpenAIRealtimeSession
from voice.providers.openai_stt import OpenAIWhisperSpeechToTextProvider
from voice.providers.openai_tts import OpenAITextToSpeechProvider
from voice.providers.openai_whisper_streaming import OpenAIWhisperStreamingSTT
from voice.providers.realtime_registry import (
    RealtimeProviderRegistry,
    get_realtime_registry,
)
from voice.providers.realtime_stt import MockRealtimeSTTProvider, RealtimeSTTProvider
from voice.providers.realtime_tts import MockRealtimeTTSProvider, RealtimeTTSProvider
from voice.providers.streaming_models import (
    AudioStreamChunk,
    StreamCapabilities,
    TranscriptHypothesis,
)
from voice.speech_to_text import SpeechToTextRegistry, get_stt_registry
from voice.text_to_speech import TextToSpeechRegistry, get_tts_registry
from voice.transport.memory import InMemoryTransport
from voice.transport.socket_backends import (
    prefer_live_transport,
    websocket_client_available,
)

logger = logging.getLogger(__name__)


def register_default_voice_providers(
    *,
    stt_registry: SpeechToTextRegistry | None = None,
    tts_registry: TextToSpeechRegistry | None = None,
    openai_client: Any | None = None,
    realtime_registry: RealtimeProviderRegistry | None = None,
) -> tuple[SpeechToTextRegistry, TextToSpeechRegistry]:
    """Register OpenAI batch STT/TTS + realtime streaming providers."""
    stt = stt_registry or get_stt_registry()
    tts = tts_registry or get_tts_registry()

    stt.register(
        OpenAIWhisperSpeechToTextProvider(
            model=app_settings.TITAN_VOICE_OPENAI_STT_MODEL,
            client=openai_client,
        )
    )
    tts.register(
        OpenAITextToSpeechProvider(
            model=app_settings.TITAN_VOICE_OPENAI_TTS_MODEL,
            client=openai_client,
        )
    )
    register_realtime_voice_providers(realtime_registry=realtime_registry)
    logger.info(
        "VOICE_PROVIDERS_REGISTERED stt=%s tts=%s realtime_stt=%s realtime_tts=%s",
        stt.list_providers(),
        tts.list_providers(),
        get_realtime_registry().list_stt(),
        get_realtime_registry().list_tts(),
    )
    return stt, tts


def register_realtime_voice_providers(
    *,
    realtime_registry: RealtimeProviderRegistry | None = None,
    prefer_live_sockets: bool | None = None,
) -> RealtimeProviderRegistry:
    """Register Phase 20.6/20.8 realtime streaming STT/TTS factories.

    When API keys + websocket-client are available and ``prefer_live_sockets``
    is true, factories build live WebSocket transports. Otherwise InMemory /
    queue backends keep tests offline-safe.
    """
    registry = realtime_registry or get_realtime_registry()
    use_live = (
        prefer_live_sockets
        if prefer_live_sockets is not None
        else bool(getattr(app_settings, "TITAN_VOICE_LIVE_SOCKETS", True))
    )

    # Always available offline mocks.
    registry.register_stt("mock_realtime_stt", MockRealtimeSTTProvider)
    registry.register_tts("mock_realtime_tts", MockRealtimeTTSProvider)

    def _whisper_streaming() -> OpenAIWhisperStreamingSTT:
        return OpenAIWhisperStreamingSTT(
            transport=InMemoryTransport(name="whisper-stream"),
            model=getattr(
                app_settings, "TITAN_VOICE_OPENAI_STT_MODEL", "whisper-1"
            ),
            transcribe_fn=lambda audio, locale: _safe_whisper_transcribe(audio, locale),
        )

    def _deepgram() -> DeepgramStreamingSTT:
        api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        model = getattr(app_settings, "TITAN_VOICE_DEEPGRAM_MODEL", "nova-2")
        transport = _provider_transport(
            use_live=use_live and bool(api_key),
            url=(
                "wss://api.deepgram.com/v1/listen"
                f"?model={model}&interim_results=true"
                "&encoding=linear16&sample_rate=16000&channels=1&punctuate=true"
            ),
            headers={"Authorization": f"Token {api_key}"} if api_key else {},
            name="deepgram",
        )
        return DeepgramStreamingSTT(api_key=api_key or None, model=model, transport=transport)

    def _eleven() -> ElevenLabsStreamingTTS:
        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        voice = getattr(app_settings, "TITAN_VOICE_ELEVENLABS_VOICE", "Rachel")
        model = getattr(
            app_settings, "TITAN_VOICE_ELEVENLABS_MODEL", "eleven_multilingual_v2"
        )
        headers: dict[str, str] = {}
        if api_key:
            headers["xi-api-key"] = api_key
        transport = _provider_transport(
            use_live=use_live and bool(api_key),
            url=(
                f"wss://api.elevenlabs.io/v1/text-to-speech/{voice}/stream-input"
                f"?model_id={model}"
            ),
            headers=headers,
            name="elevenlabs",
        )
        return ElevenLabsStreamingTTS(
            api_key=api_key or None,
            voice_id=voice,
            model_id=model,
            transport=transport,
        )

    def _openai_realtime_stt() -> RealtimeSTTProvider:
        return _OpenAIRealtimeSTTAdapter(_build_openai_realtime_session(use_live=use_live))

    def _openai_realtime_tts() -> RealtimeTTSProvider:
        return _OpenAIRealtimeTTSAdapter(_build_openai_realtime_session(use_live=use_live))

    registry.register_stt("openai_whisper_streaming", _whisper_streaming)
    registry.register_stt("deepgram_streaming", _deepgram)
    registry.register_stt("openai_realtime", _openai_realtime_stt)
    registry.register_tts("elevenlabs_streaming", _eleven)
    registry.register_tts("openai_realtime", _openai_realtime_tts)

    stt_chain = _csv(
        getattr(
            app_settings,
            "TITAN_VOICE_REALTIME_STT_FALLBACK",
            "openai_whisper_streaming,deepgram_streaming,mock_realtime_stt",
        )
    )
    tts_chain = _csv(
        getattr(
            app_settings,
            "TITAN_VOICE_REALTIME_TTS_FALLBACK",
            "elevenlabs_streaming,openai_realtime,mock_realtime_tts",
        )
    )
    registry.set_stt_fallback_chain(stt_chain)
    registry.set_tts_fallback_chain(tts_chain)
    logger.info(
        "REALTIME_PROVIDERS live_sockets=%s ws_client=%s stt=%s tts=%s",
        use_live,
        websocket_client_available(),
        registry.list_stt(),
        registry.list_tts(),
    )
    return registry


def _provider_transport(
    *,
    use_live: bool,
    url: str,
    headers: dict[str, str],
    name: str,
) -> Any:
    heartbeat = float(getattr(app_settings, "TITAN_VOICE_TRANSPORT_HEARTBEAT", 15.0))
    max_reconnect = int(getattr(app_settings, "TITAN_VOICE_TRANSPORT_RECONNECT_MAX", 5))
    if use_live and websocket_client_available():
        return prefer_live_transport(
            url=url,
            headers=headers,
            heartbeat_interval=heartbeat,
            max_reconnect=max_reconnect,
            use_live=True,
        )
    # Offline-safe default for tests / missing keys.
    return InMemoryTransport(name=name)


def _build_openai_realtime_session(*, use_live: bool) -> OpenAIRealtimeSession:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = getattr(
        app_settings, "TITAN_VOICE_OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview"
    )
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["OpenAI-Beta"] = "realtime=v1"
    transport = _provider_transport(
        use_live=use_live and bool(api_key),
        url=f"wss://api.openai.com/v1/realtime?model={model}",
        headers=headers,
        name="openai-realtime",
    )
    return OpenAIRealtimeSession(api_key=api_key or None, model=model, transport=transport)


class _OpenAIRealtimeSTTAdapter(RealtimeSTTProvider):
    """Expose OpenAI Realtime session as an STT-shaped provider for the registry."""

    def __init__(self, session: OpenAIRealtimeSession) -> None:
        super().__init__(transport=session.transport)
        self._session = session

    @property
    def provider_id(self) -> str:
        return "openai_realtime"

    @property
    def capabilities(self) -> StreamCapabilities:
        return self._session.capabilities

    def health_check(self) -> bool:
        return self._session.health_check()

    def _do_start(self, *, language: str) -> None:
        self._session.start(language=language)

    def _do_send_audio(self, audio_bytes: bytes) -> None:
        self._session.send_audio(audio_bytes)

    def _do_poll(self, *, timeout: float | None) -> TranscriptHypothesis | None:
        return self._session.poll_hypothesis(timeout=timeout)

    def _do_finish(self) -> TranscriptHypothesis | None:
        return self._session.finish_input()

    def _do_set_language(self, language: str) -> None:
        self._session.start(language=language)


class _OpenAIRealtimeTTSAdapter(RealtimeTTSProvider):
    """Expose OpenAI Realtime session as a TTS-shaped provider for the registry."""

    def __init__(self, session: OpenAIRealtimeSession) -> None:
        from voice.providers.realtime_tts import AudioBufferConfig

        super().__init__(transport=session.transport, buffer_config=AudioBufferConfig())
        self._session = session

    @property
    def provider_id(self) -> str:
        return "openai_realtime"

    @property
    def capabilities(self) -> StreamCapabilities:
        return self._session.capabilities

    def health_check(self) -> bool:
        return self._session.health_check()

    def _do_start(self, *, locale: str, voice: str) -> None:
        del voice
        if not self._session.transport.is_connected:
            self._session.start(language=locale)

    def _do_synthesize_incremental(self, text: str) -> None:
        self._session.synthesize_incremental(text)

    def _do_poll_audio(self, *, timeout: float | None) -> AudioStreamChunk | None:
        return self._session.poll_audio(timeout=timeout)

    def _do_finish(self) -> list[AudioStreamChunk]:
        leftover: list[AudioStreamChunk] = []
        while True:
            chunk = self._session.poll_audio(timeout=0.0)
            if chunk is None:
                break
            leftover.append(chunk)
        if leftover:
            leftover[-1] = AudioStreamChunk(
                audio_bytes=leftover[-1].audio_bytes,
                sequence=leftover[-1].sequence,
                mime_type=leftover[-1].mime_type,
                is_final=True,
                provider_id=self.provider_id,
            )
        return leftover


def _safe_whisper_transcribe(audio: bytes, locale: str) -> Any:
    from voice.speech_to_text import TranscriptionResult

    try:
        provider = OpenAIWhisperSpeechToTextProvider(
            model=getattr(app_settings, "TITAN_VOICE_OPENAI_STT_MODEL", "whisper-1")
        )
        if not provider.health_check():
            return TranscriptionResult(
                text="",
                duration_seconds=0.0,
                provider_id="openai_whisper_streaming",
                locale=locale,
                confidence=None,
            )
        return provider.transcribe(audio, locale=locale)
    except Exception:
        return TranscriptionResult(
            text="",
            duration_seconds=0.0,
            provider_id="openai_whisper_streaming",
            locale=locale,
            confidence=None,
        )


def _csv(raw: str) -> list[str]:
    return [part.strip().lower() for part in (raw or "").split(",") if part.strip()]

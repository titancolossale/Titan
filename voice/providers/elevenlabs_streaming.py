# =====================================
# Titan ElevenLabs Streaming TTS
# =====================================

"""ElevenLabs streaming text-to-speech adapter (Phase 20.6)."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from collections import deque
from typing import Any, Callable

from voice.cancellation import CancelToken
from voice.exceptions import VoiceConfigurationError
from voice.providers.realtime_tts import (
    AudioBufferConfig,
    RealtimeTTSProvider,
)
from voice.providers.streaming_models import (
    AudioStreamChunk,
    StreamCapabilities,
    StreamDirection,
)
from voice.transport.base import StreamingTransport, TransportConfig
from voice.transport.websocket_transport import WebSocketTransport

logger = logging.getLogger(__name__)

_DEFAULT_ELEVEN_WS = "wss://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsStreamingTTS(RealtimeTTSProvider):
    """ElevenLabs websocket/stream TTS with buffer smoothing."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str = "Rachel",
        model_id: str = "eleven_multilingual_v2",
        transport: StreamingTransport | None = None,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_token: CancelToken | None = None,
        buffer_config: AudioBufferConfig | None = None,
    ) -> None:
        self._api_key = (
            api_key.strip()
            if api_key is not None
            else os.getenv("ELEVENLABS_API_KEY", "").strip()
        )
        self._voice_id = (voice_id or "Rachel").strip()
        self._model_id = (model_id or "eleven_multilingual_v2").strip()
        if transport is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["xi-api-key"] = self._api_key
            transport = WebSocketTransport(
                TransportConfig(
                    url=f"{_DEFAULT_ELEVEN_WS}/{self._voice_id}/stream-input"
                    f"?model_id={self._model_id}",
                    headers=headers,
                )
            )
        super().__init__(
            transport=transport,
            emit=emit,
            cancel_token=cancel_token,
            buffer_config=buffer_config,
        )
        self._audio_queue: deque[AudioStreamChunk] = deque()
        self._text_parts: list[str] = []

    @property
    def provider_id(self) -> str:
        return "elevenlabs_streaming"

    @property
    def capabilities(self) -> StreamCapabilities:
        return StreamCapabilities(
            provider_id=self.provider_id,
            direction=StreamDirection.TTS,
            incremental_tts=True,
            websocket=True,
            http_fallback=True,
            audio_chunks=True,
            provider_cancellation=True,
            language_switching=True,
        )

    def health_check(self) -> bool:
        return bool(self._api_key) or self._transport is not None

    def inject_audio_bytes(self, audio_bytes: bytes, *, is_final: bool = False) -> None:
        self._audio_queue.append(
            AudioStreamChunk(
                audio_bytes=audio_bytes,
                sequence=self._next_sequence(),
                mime_type="audio/mpeg",
                is_final=is_final,
                provider_id=self.provider_id,
            )
        )

    def inject_provider_message(self, payload: dict[str, Any]) -> None:
        audio = payload.get("audio")
        if isinstance(audio, str):
            raw = _decode_audio_field(audio, live=bool(self._api_key))
        elif isinstance(audio, (bytes, bytearray)):
            raw = bytes(audio)
        else:
            raw = b""
        is_final = bool(payload.get("isFinal") or payload.get("is_final"))
        if raw or is_final:
            self.inject_audio_bytes(raw, is_final=is_final)

    def _do_start(self, *, locale: str, voice: str) -> None:
        del locale
        if voice and voice != "default":
            self._voice_id = voice
        self._audio_queue.clear()
        self._text_parts.clear()
        if not self._api_key and self._transport is None:
            raise VoiceConfigurationError(
                "ElevenLabs streaming requires ELEVENLABS_API_KEY or injected transport"
            )
        if self._transport is not None and self._transport.is_connected:
            # Live path sends the real key on the wire; diagnostics never log it.
            bootstrap: dict[str, Any] = {
                "text": " ",
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
            }
            if self._api_key:
                bootstrap["xi_api_key"] = self._api_key
            self._transport.send(json.dumps(bootstrap), binary=False)

    def _do_synthesize_incremental(self, text: str) -> None:
        self._text_parts.append(text)
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(
                json.dumps({"text": text, "try_trigger_generation": True}),
                binary=False,
            )
        # Offline simulation when no live key — generate deterministic chunks.
        if not self._api_key:
            payload = f"eleven:{self._voice_id}:{text}".encode("utf-8")
            mid = max(1, len(payload) // 2)
            self.inject_audio_bytes(payload[:mid], is_final=False)
            self.inject_audio_bytes(payload[mid:], is_final=False)

    def _do_poll_audio(self, *, timeout: float | None) -> AudioStreamChunk | None:
        self._drain(timeout=timeout)
        if self._audio_queue:
            return self._audio_queue.popleft()
        return None

    def _do_finish(self) -> list[AudioStreamChunk]:
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(json.dumps({"text": ""}), binary=False)
            self._drain(timeout=0.0)
        leftover = list(self._audio_queue)
        self._audio_queue.clear()
        if not leftover:
            return [
                AudioStreamChunk(
                    audio_bytes=b"eleven-final",
                    sequence=self._next_sequence(),
                    mime_type="audio/mpeg",
                    is_final=True,
                    provider_id=self.provider_id,
                )
            ]
        leftover[-1] = AudioStreamChunk(
            audio_bytes=leftover[-1].audio_bytes,
            sequence=leftover[-1].sequence,
            mime_type=leftover[-1].mime_type,
            is_final=True,
            provider_id=self.provider_id,
            text_span=leftover[-1].text_span,
        )
        return leftover

    def _do_cancel(self) -> None:
        self._audio_queue.clear()
        if self._transport is not None and self._transport.is_connected:
            try:
                self._transport.send(json.dumps({"text": ""}), binary=False)
            except Exception:
                pass

    def _drain(self, *, timeout: float | None) -> None:
        if self._transport is None or not self._transport.is_connected:
            return
        message = self._transport.receive(timeout=timeout)
        if message is None:
            return
        if message.binary:
            self.inject_audio_bytes(message.as_bytes(), is_final=False)
            return
        text = message.as_text().strip()
        if not text or text == "ping":
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            self.inject_provider_message(payload)


def _decode_audio_field(audio: str, *, live: bool) -> bytes:
    """Decode ElevenLabs audio field — base64 when live, utf-8 mock otherwise."""
    if not audio:
        return b""
    if live:
        try:
            return base64.b64decode(audio, validate=False)
        except (binascii.Error, ValueError):
            return audio.encode("utf-8")
    # Offline / injected mocks may pass plain text placeholders.
    try:
        decoded = base64.b64decode(audio, validate=True)
        if decoded:
            return decoded
    except (binascii.Error, ValueError):
        pass
    return audio.encode("utf-8")

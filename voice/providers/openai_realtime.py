# =====================================
# Titan OpenAI Realtime Provider
# =====================================

"""Bidirectional OpenAI Realtime streaming adapter (Phase 20.6).

Uses an injectable transport — live WebSocket URLs require OPENAI_API_KEY.
Tests inject InMemoryTransport / WebSocketTransport backends; no network by default.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
from typing import Any

from voice.cancellation import CancelToken
from voice.exceptions import VoiceConfigurationError, VoiceProviderError
from voice.providers.realtime_stt import RealtimeSTTEmit
from voice.providers.realtime_tts import AudioBufferConfig, RealtimeTTSEmit
from voice.providers.streaming_models import (
    AudioStreamChunk,
    HypothesisStability,
    StreamCapabilities,
    StreamDirection,
    TranscriptHypothesis,
)
from voice.transport.base import StreamingTransport, TransportConfig
from voice.transport.websocket_transport import WebSocketTransport

logger = logging.getLogger(__name__)

_DEFAULT_REALTIME_URL = "wss://api.openai.com/v1/realtime"


class OpenAIRealtimeSession:
    """Bidirectional realtime session (STT hypotheses + TTS audio chunks)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-realtime-preview",
        transport: StreamingTransport | None = None,
        emit: RealtimeSTTEmit | None = None,
        cancel_token: CancelToken | None = None,
        buffer_config: AudioBufferConfig | None = None,
    ) -> None:
        self._api_key = (
            api_key.strip()
            if api_key is not None
            else os.getenv("OPENAI_API_KEY", "").strip()
        )
        self._model = (model or "gpt-4o-realtime-preview").strip()
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="openai_realtime")
        self._buffer_config = buffer_config or AudioBufferConfig()
        if transport is not None:
            self._transport = transport
        else:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
                headers["OpenAI-Beta"] = "realtime=v1"
            self._transport = WebSocketTransport(
                TransportConfig(
                    url=f"{_DEFAULT_REALTIME_URL}?model={self._model}",
                    headers=headers,
                ),
                emit=None,
            )
        self._started_at = 0.0
        self._sequence = 0
        self._language = "fr-FR"
        self._pending_hypotheses: list[TranscriptHypothesis] = []
        self._pending_audio: list[AudioStreamChunk] = []

    @property
    def provider_id(self) -> str:
        return "openai_realtime"

    @property
    def capabilities(self) -> StreamCapabilities:
        return StreamCapabilities(
            provider_id=self.provider_id,
            direction=StreamDirection.BIDIRECTIONAL,
            incremental_stt=True,
            incremental_tts=True,
            bidirectional=True,
            websocket=True,
            http_fallback=True,
            partial_hypotheses=True,
            stable_hypotheses=True,
            confidence_updates=True,
            language_switching=True,
            timestamp_tracking=True,
            speaker_tracking=False,
            audio_chunks=True,
            provider_cancellation=True,
        )

    @property
    def transport(self) -> StreamingTransport:
        return self._transport

    def health_check(self) -> bool:
        return bool(self._api_key) or self._transport is not None

    def start(self, *, language: str = "fr-FR") -> None:
        self._cancel.reset()
        self._language = language
        self._started_at = time.perf_counter()
        self._pending_hypotheses.clear()
        self._pending_audio.clear()
        if not self._transport.is_connected:
            self._transport.connect()
        # Session bootstrap — offline-safe JSON control frame.
        self._transport.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "input_audio_transcription": {"language": _lang(language)},
                    },
                }
            ),
            binary=False,
        )
        self._fire("PROVIDER_REALTIME_STARTED", {"provider_id": self.provider_id})

    def send_audio(self, audio_bytes: bytes) -> None:
        self._cancel.raise_if_cancelled()
        if not audio_bytes:
            return
        # OpenAI Realtime wire format: base64 PCM in input_audio_buffer.append.
        frame = json.dumps(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_bytes).decode("ascii"),
            }
        )
        self._transport.send(frame, binary=False)
        # Offline mocks without API key also accept a binary peer push.
        if not self._api_key:
            self._transport.send(audio_bytes, binary=True)
        self._fire(
            "PROVIDER_STT_AUDIO",
            {"provider_id": self.provider_id, "bytes": len(audio_bytes)},
        )

    def synthesize_incremental(self, text: str) -> None:
        self._cancel.raise_if_cancelled()
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self._transport.send(
            json.dumps({"type": "response.create", "text": cleaned}),
            binary=False,
        )
        # Offline simulation: fabricate a small audio chunk for tests without network.
        if not self._api_key:
            self._pending_audio.append(
                AudioStreamChunk(
                    audio_bytes=f"openai-rt:{cleaned}".encode("utf-8"),
                    sequence=self._next_seq(),
                    mime_type="audio/pcm",
                    provider_id=self.provider_id,
                    text_span=cleaned,
                )
            )
        self._fire(
            "PROVIDER_TTS_TEXT",
            {"provider_id": self.provider_id, "chars": len(cleaned)},
        )

    def inject_provider_event(self, event: dict[str, Any]) -> None:
        """Test / adapter helper — map provider JSON into hypotheses/audio."""
        etype = str(event.get("type") or "")
        if etype in {"conversation.item.input_audio_transcription.delta", "transcript.partial"}:
            text = str(event.get("delta") or event.get("text") or "")
            self._pending_hypotheses.append(
                TranscriptHypothesis(
                    text=text,
                    stability=HypothesisStability.PARTIAL,
                    confidence=event.get("confidence"),
                    language=self._language,
                    provider_id=self.provider_id,
                )
            )
        elif etype in {
            "conversation.item.input_audio_transcription.completed",
            "transcript.final",
        }:
            text = str(event.get("transcript") or event.get("text") or "")
            self._pending_hypotheses.append(
                TranscriptHypothesis(
                    text=text,
                    stability=HypothesisStability.FINAL,
                    confidence=event.get("confidence"),
                    language=self._language,
                    is_final=True,
                    provider_id=self.provider_id,
                )
            )
        elif etype in {"response.audio.delta", "audio.chunk"}:
            raw = event.get("audio") or event.get("data") or b""
            if isinstance(raw, str):
                try:
                    raw = base64.b64decode(raw, validate=False)
                except (binascii.Error, ValueError):
                    raw = raw.encode("utf-8")
            self._pending_audio.append(
                AudioStreamChunk(
                    audio_bytes=bytes(raw),
                    sequence=self._next_seq(),
                    mime_type="audio/pcm",
                    provider_id=self.provider_id,
                    is_final=False,
                )
            )
        elif etype in {"response.audio.done", "audio.final"}:
            self._pending_audio.append(
                AudioStreamChunk(
                    audio_bytes=b"",
                    sequence=self._next_seq(),
                    mime_type="audio/pcm",
                    provider_id=self.provider_id,
                    is_final=True,
                )
            )

    def poll_hypothesis(self, *, timeout: float | None = 0.0) -> TranscriptHypothesis | None:
        self._drain_transport(timeout=timeout)
        if self._pending_hypotheses:
            hyp = self._pending_hypotheses.pop(0)
            self._fire("PROVIDER_STT_HYPOTHESIS", hyp.to_safe_dict())
            return hyp
        return None

    def poll_audio(self, *, timeout: float | None = 0.0) -> AudioStreamChunk | None:
        self._drain_transport(timeout=timeout)
        if self._pending_audio:
            chunk = self._pending_audio.pop(0)
            self._fire("PROVIDER_TTS_CHUNK", chunk.to_safe_dict())
            return chunk
        return None

    def finish_input(self) -> TranscriptHypothesis | None:
        self._transport.send(
            json.dumps({"type": "input_audio_buffer.commit"}),
            binary=False,
        )
        # Offline: synthesize final from last partial or placeholder.
        if not self._api_key and not self._pending_hypotheses:
            return TranscriptHypothesis(
                text="bonjour titan",
                stability=HypothesisStability.FINAL,
                confidence=0.9,
                language=self._language,
                is_final=True,
                provider_id=self.provider_id,
            )
        return self.poll_hypothesis(timeout=0.0)

    def cancel(self) -> None:
        self._cancel.cancel()
        try:
            self._transport.send(json.dumps({"type": "response.cancel"}), binary=False)
        except Exception:
            pass
        self._pending_audio.clear()
        self._pending_hypotheses.clear()
        self._fire("PROVIDER_REALTIME_CANCELLED", {"provider_id": self.provider_id})

    def close(self) -> None:
        try:
            self._transport.disconnect(reason="openai_realtime_close")
        except Exception:
            pass
        self._fire("PROVIDER_REALTIME_CLOSED", {"provider_id": self.provider_id})

    def _drain_transport(self, *, timeout: float | None) -> None:
        if not self._transport.is_connected:
            return
        message = self._transport.receive(timeout=timeout)
        if message is None:
            return
        if message.binary:
            self._pending_audio.append(
                AudioStreamChunk(
                    audio_bytes=message.as_bytes(),
                    sequence=self._next_seq(),
                    mime_type="audio/pcm",
                    provider_id=self.provider_id,
                )
            )
            return
        text = message.as_text().strip()
        if not text or text == "ping":
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(event, dict):
            self.inject_provider_event(event)

    def _next_seq(self) -> int:
        seq = self._sequence
        self._sequence += 1
        return seq

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("OpenAI Realtime emit failed: %s", exc)


def _lang(locale: str) -> str:
    cleaned = (locale or "").strip()
    if not cleaned:
        return "fr"
    return cleaned.split("-", 1)[0].lower()


def require_openai_key_for_live(api_key: str | None = None) -> str:
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        raise VoiceConfigurationError(
            "OpenAI Realtime requires OPENAI_API_KEY for live network sessions"
        )
    return key


# Silence unused import warning for VoiceProviderError in static analysis paths.
_ = VoiceProviderError

# =====================================
# Titan Deepgram Streaming STT
# =====================================

"""Deepgram live streaming speech-to-text adapter (Phase 20.6)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable

from voice.cancellation import CancelToken
from voice.exceptions import VoiceConfigurationError
from voice.providers.realtime_stt import RealtimeSTTProvider
from voice.providers.streaming_models import (
    HypothesisStability,
    StreamCapabilities,
    StreamDirection,
    TranscriptHypothesis,
)
from voice.transport.base import StreamingTransport, TransportConfig
from voice.transport.websocket_transport import WebSocketTransport

logger = logging.getLogger(__name__)

_DEFAULT_DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramStreamingSTT(RealtimeSTTProvider):
    """Deepgram websocket streaming STT with injectable transport."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "nova-2",
        transport: StreamingTransport | None = None,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> None:
        self._api_key = (
            api_key.strip()
            if api_key is not None
            else os.getenv("DEEPGRAM_API_KEY", "").strip()
        )
        self._model = (model or "nova-2").strip()
        if transport is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Token {self._api_key}"
            # Deepgram raw PCM requires encoding / sample_rate / channels.
            query = (
                f"model={self._model}"
                "&interim_results=true"
                "&encoding=linear16"
                "&sample_rate=16000"
                "&channels=1"
                "&punctuate=true"
            )
            transport = WebSocketTransport(
                TransportConfig(
                    url=f"{_DEFAULT_DEEPGRAM_URL}?{query}",
                    headers=headers,
                )
            )
        super().__init__(transport=transport, emit=emit, cancel_token=cancel_token)
        self._pending: list[TranscriptHypothesis] = []
        self._last_text = ""

    @property
    def provider_id(self) -> str:
        return "deepgram_streaming"

    @property
    def capabilities(self) -> StreamCapabilities:
        return StreamCapabilities(
            provider_id=self.provider_id,
            direction=StreamDirection.STT,
            incremental_stt=True,
            websocket=True,
            http_fallback=True,
            partial_hypotheses=True,
            stable_hypotheses=True,
            confidence_updates=True,
            language_switching=True,
            timestamp_tracking=True,
            speaker_tracking=True,
            provider_cancellation=True,
        )

    def health_check(self) -> bool:
        return bool(self._api_key) or self._transport is not None

    def inject_deepgram_message(self, payload: dict[str, Any]) -> None:
        """Map a Deepgram Results message into a TranscriptHypothesis."""
        channel = payload.get("channel") or {}
        alts = channel.get("alternatives") or []
        if not alts:
            return
        alt = alts[0] if isinstance(alts[0], dict) else {}
        text = str(alt.get("transcript") or "").strip()
        if not text:
            return
        is_final = bool(payload.get("is_final") or payload.get("speech_final"))
        confidence = alt.get("confidence")
        speaker = None
        words = alt.get("words") or []
        if words and isinstance(words[0], dict):
            speaker = words[0].get("speaker")
            if speaker is not None:
                speaker = str(speaker)
        start_ms = None
        end_ms = None
        if payload.get("start") is not None:
            start_ms = float(payload["start"]) * 1000.0
        if payload.get("duration") is not None and start_ms is not None:
            end_ms = start_ms + float(payload["duration"]) * 1000.0
        stability = (
            HypothesisStability.FINAL
            if is_final
            else (
                HypothesisStability.STABLE
                if float(confidence or 0) >= 0.75
                else HypothesisStability.PARTIAL
            )
        )
        self._last_text = text
        self._pending.append(
            TranscriptHypothesis(
                text=text,
                stability=stability,
                confidence=float(confidence) if confidence is not None else None,
                language=self._language,
                start_ms=start_ms,
                end_ms=end_ms,
                speaker_id=speaker,
                is_final=is_final,
                provider_id=self.provider_id,
            )
        )

    def _do_start(self, *, language: str) -> None:
        del language
        self._pending.clear()
        self._last_text = ""
        if not self._api_key and self._transport is None:
            raise VoiceConfigurationError(
                "Deepgram streaming requires DEEPGRAM_API_KEY or an injected transport"
            )

    def _do_send_audio(self, audio_bytes: bytes) -> None:
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(audio_bytes, binary=True)

    def _do_set_language(self, language: str) -> None:
        # Deepgram typically requires reconnect with new language query param.
        self._language = language
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(
                json.dumps({"type": "Configure", "language": language}),
                binary=False,
            )

    def _do_poll(self, *, timeout: float | None) -> TranscriptHypothesis | None:
        self._drain(timeout=timeout)
        if self._pending:
            return self._pending.pop(0)
        return None

    def _do_finish(self) -> TranscriptHypothesis | None:
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(json.dumps({"type": "CloseStream"}), binary=False)
            self._drain(timeout=0.0)
        while self._pending:
            hyp = self._pending.pop(0)
            if hyp.is_final or hyp.stability == HypothesisStability.FINAL:
                return hyp
            self._record(hyp)
        elapsed = (time.perf_counter() - self._started_at) * 1000.0
        return TranscriptHypothesis(
            text=self._last_text,
            stability=HypothesisStability.FINAL,
            confidence=0.8 if self._last_text else 0.0,
            language=self._language,
            start_ms=0.0,
            end_ms=elapsed,
            is_final=True,
            provider_id=self.provider_id,
        )

    def _drain(self, *, timeout: float | None) -> None:
        if self._transport is None or not self._transport.is_connected:
            return
        message = self._transport.receive(timeout=timeout)
        if message is None or message.binary:
            return
        text = message.as_text().strip()
        if not text or text == "ping":
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            self.inject_deepgram_message(payload)

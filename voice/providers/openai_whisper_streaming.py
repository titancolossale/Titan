# =====================================
# Titan OpenAI Whisper Streaming STT
# =====================================

"""Chunked / streaming Whisper STT adapter (Phase 20.6).

Whisper's public API is batch-oriented; this adapter streams audio into a
transport, emits progressive partial/stable estimates, then runs a final
transcription via the existing OpenAI Whisper provider (or injected callable).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from voice.cancellation import CancelToken
from voice.providers.openai_stt import OpenAIWhisperSpeechToTextProvider
from voice.providers.realtime_stt import RealtimeSTTProvider
from voice.providers.streaming_models import (
    HypothesisStability,
    StreamCapabilities,
    StreamDirection,
    TranscriptHypothesis,
)
from voice.speech_to_text import TranscriptionResult
from voice.transport.base import StreamingTransport

logger = logging.getLogger(__name__)

TranscribeFn = Callable[[bytes, str], TranscriptionResult]


class OpenAIWhisperStreamingSTT(RealtimeSTTProvider):
    """Incremental wrapper around Whisper with transport-backed audio uplink."""

    def __init__(
        self,
        *,
        transport: StreamingTransport | None = None,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_token: CancelToken | None = None,
        whisper: OpenAIWhisperSpeechToTextProvider | None = None,
        transcribe_fn: TranscribeFn | None = None,
        model: str = "whisper-1",
    ) -> None:
        super().__init__(transport=transport, emit=emit, cancel_token=cancel_token)
        self._whisper = whisper or OpenAIWhisperSpeechToTextProvider(model=model)
        self._transcribe_fn = transcribe_fn
        self._buffer = bytearray()
        self._pending: list[TranscriptHypothesis] = []
        self._partial_emitted = False
        self._stable_emitted = False

    @property
    def provider_id(self) -> str:
        return "openai_whisper_streaming"

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
            speaker_tracking=False,
            provider_cancellation=True,
        )

    def health_check(self) -> bool:
        return self._whisper.health_check()

    def _do_start(self, *, language: str) -> None:
        del language
        self._buffer.clear()
        self._pending.clear()
        self._partial_emitted = False
        self._stable_emitted = False

    def _do_send_audio(self, audio_bytes: bytes) -> None:
        self._buffer.extend(audio_bytes)
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(audio_bytes, binary=True)
        elapsed = (time.perf_counter() - self._started_at) * 1000.0
        if not self._partial_emitted and len(self._buffer) >= 1600:
            self._pending.append(
                TranscriptHypothesis(
                    text="…",
                    stability=HypothesisStability.PARTIAL,
                    confidence=0.3,
                    language=self._language,
                    start_ms=0.0,
                    end_ms=elapsed,
                    provider_id=self.provider_id,
                )
            )
            self._partial_emitted = True
        if not self._stable_emitted and len(self._buffer) >= 8000:
            # Optional mid-stream re-transcribe when callable is cheap/mocked.
            stable_text = "…"
            confidence = 0.55
            if self._transcribe_fn is not None:
                try:
                    result = self._transcribe_fn(bytes(self._buffer), self._language or "fr-FR")
                    stable_text = (result.text or "").strip() or stable_text
                    confidence = result.confidence if result.confidence is not None else confidence
                except Exception as exc:
                    logger.warning("Whisper streaming stable pass failed: %s", exc)
            self._pending.append(
                TranscriptHypothesis(
                    text=stable_text,
                    stability=HypothesisStability.STABLE,
                    confidence=confidence,
                    language=self._language,
                    start_ms=0.0,
                    end_ms=elapsed,
                    provider_id=self.provider_id,
                )
            )
            self._stable_emitted = True

    def _do_poll(self, *, timeout: float | None) -> TranscriptHypothesis | None:
        del timeout
        if self._pending:
            return self._pending.pop(0)
        return None

    def _do_finish(self) -> TranscriptHypothesis | None:
        while self._pending:
            self._record(self._pending.pop(0))
        audio = bytes(self._buffer)
        if not audio:
            return TranscriptHypothesis(
                text="",
                stability=HypothesisStability.FINAL,
                confidence=0.0,
                language=self._language,
                is_final=True,
                provider_id=self.provider_id,
            )
        if self._transcribe_fn is not None:
            result = self._transcribe_fn(audio, self._language or "fr-FR")
        else:
            # Prefer injected whisper client; may raise without API key — callers
            # should inject transcribe_fn in tests / offline.
            result = self._whisper.transcribe(audio, locale=self._language or "fr-FR")
        elapsed = (time.perf_counter() - self._started_at) * 1000.0
        return TranscriptHypothesis(
            text=(result.text or "").strip(),
            stability=HypothesisStability.FINAL,
            confidence=result.confidence,
            language=self._language,
            start_ms=0.0,
            end_ms=elapsed,
            is_final=True,
            provider_id=self.provider_id,
        )

    def _do_cancel(self) -> None:
        self._pending.clear()

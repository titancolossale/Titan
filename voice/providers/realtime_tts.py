# =====================================
# Titan Realtime TTS Provider Interface
# =====================================

"""Provider-level incremental speech synthesis (Phase 20.6)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from voice.cancellation import CancelToken
from voice.providers.streaming_models import (
    AudioStreamChunk,
    ProviderLatencyMarks,
    StreamCapabilities,
    StreamDirection,
)
from voice.transport.base import StreamingTransport

logger = logging.getLogger(__name__)

RealtimeTTSEmit = Callable[[str, dict[str, Any]], None]


@dataclass
class AudioBufferConfig:
    """Smoothing / sync knobs for low-latency playback."""

    target_buffer_ms: float = 80.0
    max_buffer_ms: float = 400.0
    min_chunk_bytes: int = 256
    max_pending_chunks: int = 32
    drop_oldest_on_overflow: bool = True


@dataclass
class SmoothedAudioBuffer:
    """Jitter buffer that smooths provider chunk arrival for playback."""

    config: AudioBufferConfig = field(default_factory=AudioBufferConfig)
    _pending: deque[AudioStreamChunk] = field(default_factory=deque)
    _bytes: int = 0

    def push(self, chunk: AudioStreamChunk) -> None:
        if len(self._pending) >= self.config.max_pending_chunks:
            if self.config.drop_oldest_on_overflow and self._pending:
                dropped = self._pending.popleft()
                self._bytes -= len(dropped.audio_bytes)
            else:
                return
        self._pending.append(chunk)
        self._bytes += len(chunk.audio_bytes)

    def pop_ready(self, *, force: bool = False) -> AudioStreamChunk | None:
        if not self._pending:
            return None
        head = self._pending[0]
        if force or len(head.audio_bytes) >= self.config.min_chunk_bytes or head.is_final:
            chunk = self._pending.popleft()
            self._bytes -= len(chunk.audio_bytes)
            return chunk
        # Accumulate small chunks into one smoothed frame.
        if self._bytes >= self.config.min_chunk_bytes:
            parts: list[bytes] = []
            mime = head.mime_type
            provider_id = head.provider_id
            sequence = head.sequence
            sample_rate = head.sample_rate
            is_final = False
            while self._pending and sum(len(p) for p in parts) < self.config.min_chunk_bytes:
                item = self._pending.popleft()
                self._bytes -= len(item.audio_bytes)
                parts.append(item.audio_bytes)
                is_final = item.is_final
                if item.is_final:
                    break
            return AudioStreamChunk(
                audio_bytes=b"".join(parts),
                sequence=sequence,
                mime_type=mime,
                sample_rate=sample_rate,
                is_final=is_final,
                provider_id=provider_id,
            )
        return None

    def clear(self) -> None:
        self._pending.clear()
        self._bytes = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def pending_bytes(self) -> int:
        return self._bytes


class RealtimeTTSProvider(ABC):
    """Incremental TTS over a streaming transport."""

    def __init__(
        self,
        *,
        transport: StreamingTransport | None = None,
        emit: RealtimeTTSEmit | None = None,
        cancel_token: CancelToken | None = None,
        buffer_config: AudioBufferConfig | None = None,
    ) -> None:
        self._transport = transport
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="realtime_tts")
        self._buffer = SmoothedAudioBuffer(config=buffer_config or AudioBufferConfig())
        self._started_at = 0.0
        self._latency = ProviderLatencyMarks()
        self._sequence = 0
        self._chunks: list[AudioStreamChunk] = []
        self._locale = "fr-FR"
        self._voice = "default"

    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...

    @property
    @abstractmethod
    def capabilities(self) -> StreamCapabilities:
        ...

    @property
    def cancel_token(self) -> CancelToken:
        return self._cancel

    @property
    def latency(self) -> ProviderLatencyMarks:
        return self._latency

    @property
    def buffer(self) -> SmoothedAudioBuffer:
        return self._buffer

    def start(self, *, locale: str = "fr-FR", voice: str = "default") -> None:
        self._cancel.reset()
        self._locale = locale
        self._voice = voice
        self._started_at = time.perf_counter()
        self._latency = ProviderLatencyMarks()
        self._sequence = 0
        self._chunks.clear()
        self._buffer.clear()
        if self._transport is not None and not self._transport.is_connected:
            self._transport.connect()
        self._do_start(locale=locale, voice=voice)
        self._fire(
            "PROVIDER_TTS_STARTED",
            {"provider_id": self.provider_id, "locale": locale, "voice": voice},
        )

    def synthesize_incremental(self, text: str) -> None:
        """Push text for incremental synthesis (may emit audio asynchronously)."""
        self._cancel.raise_if_cancelled()
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self._do_synthesize_incremental(cleaned)
        self._fire(
            "PROVIDER_TTS_TEXT",
            {"provider_id": self.provider_id, "chars": len(cleaned)},
        )

    def poll_audio(self, *, timeout: float | None = 0.0, force: bool = False) -> AudioStreamChunk | None:
        self._cancel.raise_if_cancelled()
        raw = self._do_poll_audio(timeout=timeout)
        if raw is not None:
            if not self._latency.provider_first_audio_ms:
                self._latency.provider_first_audio_ms = (
                    time.perf_counter() - self._started_at
                ) * 1000.0
            self._buffer.push(raw)
            self._chunks.append(raw)
            self._fire(
                "PROVIDER_TTS_CHUNK",
                {"provider_id": self.provider_id, **raw.to_safe_dict()},
            )
        return self._buffer.pop_ready(force=force)

    def iter_audio(
        self, *, timeout: float | None = 0.05, max_idle_polls: int = 5
    ) -> Iterator[AudioStreamChunk]:
        idle = 0
        while not self._cancel.cancelled and idle < max_idle_polls:
            chunk = self.poll_audio(timeout=timeout)
            if chunk is None:
                idle += 1
                continue
            idle = 0
            yield chunk
            if chunk.is_final:
                break

    def finish(self) -> list[AudioStreamChunk]:
        self._cancel.raise_if_cancelled()
        final_chunks = self._do_finish()
        out: list[AudioStreamChunk] = []
        for chunk in final_chunks:
            if not self._latency.provider_first_audio_ms:
                self._latency.provider_first_audio_ms = (
                    time.perf_counter() - self._started_at
                ) * 1000.0
            self._buffer.push(chunk)
            self._chunks.append(chunk)
        while True:
            ready = self._buffer.pop_ready(force=True)
            if ready is None:
                break
            out.append(ready)
            self._fire(
                "PROVIDER_TTS_CHUNK",
                {"provider_id": self.provider_id, **ready.to_safe_dict()},
            )
        self._latency.round_trip_ms = (
            (time.perf_counter() - self._started_at) * 1000.0 if self._started_at else 0.0
        )
        self._fire(
            "PROVIDER_TTS_COMPLETED",
            {
                "provider_id": self.provider_id,
                "chunk_count": len(out),
                "latency": self._latency.to_dict(),
            },
        )
        return out

    def cancel(self) -> None:
        self._cancel.cancel()
        self._buffer.clear()
        self._do_cancel()
        self._fire("PROVIDER_TTS_CANCELLED", {"provider_id": self.provider_id})

    def close(self) -> None:
        self._do_close()
        if self._transport is not None:
            try:
                self._transport.disconnect(reason="tts_close")
            except Exception:
                pass
        self._fire("PROVIDER_TTS_CLOSED", {"provider_id": self.provider_id})

    def health_check(self) -> bool:
        return True

    def _next_sequence(self) -> int:
        seq = self._sequence
        self._sequence += 1
        return seq

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("Realtime TTS emit failed: %s", exc)

    @abstractmethod
    def _do_start(self, *, locale: str, voice: str) -> None:
        ...

    @abstractmethod
    def _do_synthesize_incremental(self, text: str) -> None:
        ...

    @abstractmethod
    def _do_poll_audio(self, *, timeout: float | None) -> AudioStreamChunk | None:
        ...

    @abstractmethod
    def _do_finish(self) -> list[AudioStreamChunk]:
        ...

    def _do_cancel(self) -> None:
        return None

    def _do_close(self) -> None:
        return None


class MockRealtimeTTSProvider(RealtimeTTSProvider):
    """Deterministic byte-stream TTS for tests."""

    def __init__(
        self,
        *,
        transport: StreamingTransport | None = None,
        emit: RealtimeTTSEmit | None = None,
        cancel_token: CancelToken | None = None,
        buffer_config: AudioBufferConfig | None = None,
        chunk_size: int = 64,
    ) -> None:
        super().__init__(
            transport=transport,
            emit=emit,
            cancel_token=cancel_token,
            buffer_config=buffer_config,
        )
        self._chunk_size = max(8, chunk_size)
        self._pending_text: list[str] = []
        self._audio_queue: deque[AudioStreamChunk] = deque()

    @property
    def provider_id(self) -> str:
        return "mock_realtime_tts"

    @property
    def capabilities(self) -> StreamCapabilities:
        return StreamCapabilities(
            provider_id=self.provider_id,
            direction=StreamDirection.TTS,
            incremental_tts=True,
            audio_chunks=True,
            provider_cancellation=True,
            http_fallback=True,
        )

    def _do_start(self, *, locale: str, voice: str) -> None:
        del locale, voice
        self._pending_text.clear()
        self._audio_queue.clear()

    def _do_synthesize_incremental(self, text: str) -> None:
        self._pending_text.append(text)
        payload = f"mock-stream:{self._locale}:{self._voice}:{text}".encode("utf-8")
        for i in range(0, len(payload), self._chunk_size):
            piece = payload[i : i + self._chunk_size]
            self._audio_queue.append(
                AudioStreamChunk(
                    audio_bytes=piece,
                    sequence=self._next_sequence(),
                    mime_type="audio/mpeg",
                    is_final=False,
                    provider_id=self.provider_id,
                    text_span=text,
                )
            )
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(payload, binary=True)

    def _do_poll_audio(self, *, timeout: float | None) -> AudioStreamChunk | None:
        del timeout
        if self._audio_queue:
            return self._audio_queue.popleft()
        return None

    def _do_finish(self) -> list[AudioStreamChunk]:
        leftover = list(self._audio_queue)
        self._audio_queue.clear()
        if leftover:
            leftover[-1] = AudioStreamChunk(
                audio_bytes=leftover[-1].audio_bytes,
                sequence=leftover[-1].sequence,
                mime_type=leftover[-1].mime_type,
                is_final=True,
                provider_id=self.provider_id,
                text_span=leftover[-1].text_span,
            )
            return leftover
        marker = AudioStreamChunk(
            audio_bytes=b"mock-final",
            sequence=self._next_sequence(),
            mime_type="audio/mpeg",
            is_final=True,
            provider_id=self.provider_id,
        )
        return [marker]

    def _do_cancel(self) -> None:
        self._audio_queue.clear()
        self._pending_text.clear()

# =====================================
# Titan Realtime STT Provider Interface
# =====================================

"""Provider-level incremental speech recognition (Phase 20.6)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator

from voice.cancellation import CancelToken
from voice.providers.streaming_models import (
    HypothesisStability,
    ProviderLatencyMarks,
    StreamCapabilities,
    StreamDirection,
    TranscriptHypothesis,
)
from voice.transport.base import StreamingTransport

logger = logging.getLogger(__name__)

RealtimeSTTEmit = Callable[[str, dict[str, Any]], None]


class RealtimeSTTProvider(ABC):
    """Incremental STT over a streaming transport."""

    def __init__(
        self,
        *,
        transport: StreamingTransport | None = None,
        emit: RealtimeSTTEmit | None = None,
        cancel_token: CancelToken | None = None,
    ) -> None:
        self._transport = transport
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="realtime_stt")
        self._language: str | None = None
        self._started_at = 0.0
        self._latency = ProviderLatencyMarks()
        self._hypotheses: list[TranscriptHypothesis] = []

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
    def hypotheses(self) -> list[TranscriptHypothesis]:
        return list(self._hypotheses)

    def start(self, *, language: str = "fr-FR") -> None:
        self._cancel.reset()
        self._language = language
        self._started_at = time.perf_counter()
        self._latency = ProviderLatencyMarks()
        self._hypotheses.clear()
        if self._transport is not None and not self._transport.is_connected:
            self._transport.connect()
        self._do_start(language=language)
        self._fire(
            "PROVIDER_STT_STARTED",
            {"provider_id": self.provider_id, "language": language},
        )

    def send_audio(self, audio_bytes: bytes, *, mic_capture_ms: float | None = None) -> None:
        self._cancel.raise_if_cancelled()
        if not audio_bytes:
            return
        if mic_capture_ms is not None and not self._latency.mic_to_send_ms:
            self._latency.mic_to_send_ms = max(
                0.0, (time.perf_counter() - self._started_at) * 1000.0 - mic_capture_ms
            )
        send_started = time.perf_counter()
        self._do_send_audio(audio_bytes)
        if not self._latency.mic_to_send_ms:
            self._latency.mic_to_send_ms = (time.perf_counter() - send_started) * 1000.0
        self._fire(
            "PROVIDER_STT_AUDIO",
            {"provider_id": self.provider_id, "bytes": len(audio_bytes)},
        )

    def set_language(self, language: str) -> None:
        """Hot language switch when supported."""
        self._language = language
        self._do_set_language(language)
        self._fire(
            "PROVIDER_STT_LANGUAGE",
            {"provider_id": self.provider_id, "language": language},
        )

    def poll(self, *, timeout: float | None = 0.0) -> TranscriptHypothesis | None:
        self._cancel.raise_if_cancelled()
        hyp = self._do_poll(timeout=timeout)
        if hyp is None:
            return None
        return self._record(hyp)

    def iter_hypotheses(
        self, *, timeout: float | None = 0.05, max_idle_polls: int = 3
    ) -> Iterator[TranscriptHypothesis]:
        idle = 0
        while not self._cancel.cancelled and idle < max_idle_polls:
            hyp = self.poll(timeout=timeout)
            if hyp is None:
                idle += 1
                continue
            idle = 0
            yield hyp
            if hyp.is_final or hyp.stability == HypothesisStability.FINAL:
                break

    def finish(self) -> TranscriptHypothesis | None:
        self._cancel.raise_if_cancelled()
        hyp = self._do_finish()
        if hyp is not None:
            hyp = self._record(hyp)
        elapsed = (time.perf_counter() - self._started_at) * 1000.0 if self._started_at else 0.0
        self._latency.provider_final_ms = elapsed
        self._latency.round_trip_ms = elapsed
        self._fire(
            "PROVIDER_STT_FINAL",
            {
                "provider_id": self.provider_id,
                "latency": self._latency.to_dict(),
                "hypothesis_count": len(self._hypotheses),
            },
        )
        return hyp

    def cancel(self) -> None:
        self._cancel.cancel()
        self._do_cancel()
        self._fire("PROVIDER_STT_CANCELLED", {"provider_id": self.provider_id})

    def close(self) -> None:
        self._do_close()
        if self._transport is not None:
            try:
                self._transport.disconnect(reason="stt_close")
            except Exception:
                pass
        self._fire("PROVIDER_STT_CLOSED", {"provider_id": self.provider_id})

    def health_check(self) -> bool:
        return True

    def _record(self, hyp: TranscriptHypothesis) -> TranscriptHypothesis:
        elapsed = (time.perf_counter() - self._started_at) * 1000.0 if self._started_at else 0.0
        if hyp.stability == HypothesisStability.PARTIAL and not self._latency.provider_first_partial_ms:
            self._latency.provider_first_partial_ms = elapsed
        if hyp.stability == HypothesisStability.STABLE and not self._latency.provider_first_stable_ms:
            self._latency.provider_first_stable_ms = elapsed
        if hyp.stability == HypothesisStability.FINAL or hyp.is_final:
            self._latency.provider_final_ms = elapsed
        self._hypotheses.append(hyp)
        self._fire(
            "PROVIDER_STT_HYPOTHESIS",
            {"provider_id": self.provider_id, **hyp.to_safe_dict()},
        )
        return hyp

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("Realtime STT emit failed: %s", exc)

    @abstractmethod
    def _do_start(self, *, language: str) -> None:
        ...

    @abstractmethod
    def _do_send_audio(self, audio_bytes: bytes) -> None:
        ...

    def _do_set_language(self, language: str) -> None:
        del language

    @abstractmethod
    def _do_poll(self, *, timeout: float | None) -> TranscriptHypothesis | None:
        ...

    @abstractmethod
    def _do_finish(self) -> TranscriptHypothesis | None:
        ...

    def _do_cancel(self) -> None:
        return None

    def _do_close(self) -> None:
        return None


class MockRealtimeSTTProvider(RealtimeSTTProvider):
    """Deterministic incremental STT for tests — progressive partial → stable → final."""

    def __init__(
        self,
        *,
        final_text: str = "bonjour titan",
        transport: StreamingTransport | None = None,
        emit: RealtimeSTTEmit | None = None,
        cancel_token: CancelToken | None = None,
        progressive: bool = True,
    ) -> None:
        super().__init__(transport=transport, emit=emit, cancel_token=cancel_token)
        self._final_text = final_text
        self._progressive = progressive
        self._buffer = bytearray()
        self._emitted_partial = False
        self._emitted_stable = False
        self._pending: list[TranscriptHypothesis] = []
        self._speaker_id: str | None = None

    @property
    def provider_id(self) -> str:
        return "mock_realtime_stt"

    @property
    def capabilities(self) -> StreamCapabilities:
        return StreamCapabilities(
            provider_id=self.provider_id,
            direction=StreamDirection.STT,
            incremental_stt=True,
            partial_hypotheses=True,
            stable_hypotheses=True,
            confidence_updates=True,
            language_switching=True,
            timestamp_tracking=True,
            speaker_tracking=True,
            http_fallback=True,
            provider_cancellation=True,
        )

    def set_speaker_id(self, speaker_id: str | None) -> None:
        self._speaker_id = speaker_id

    def _do_start(self, *, language: str) -> None:
        del language
        self._buffer.clear()
        self._emitted_partial = False
        self._emitted_stable = False
        self._pending.clear()

    def _do_send_audio(self, audio_bytes: bytes) -> None:
        self._buffer.extend(audio_bytes)
        elapsed = (time.perf_counter() - self._started_at) * 1000.0
        if self._progressive and not self._emitted_partial and len(self._buffer) >= 800:
            self._pending.append(
                TranscriptHypothesis(
                    text="…",
                    stability=HypothesisStability.PARTIAL,
                    confidence=0.35,
                    language=self._language,
                    start_ms=0.0,
                    end_ms=elapsed,
                    speaker_id=self._speaker_id,
                    provider_id=self.provider_id,
                )
            )
            self._emitted_partial = True
        if self._progressive and not self._emitted_stable and len(self._buffer) >= 3200:
            words = self._final_text.split()
            stable = " ".join(words[: max(1, len(words) // 2)]) if words else self._final_text
            self._pending.append(
                TranscriptHypothesis(
                    text=stable,
                    stability=HypothesisStability.STABLE,
                    confidence=0.72,
                    language=self._language,
                    start_ms=0.0,
                    end_ms=elapsed,
                    speaker_id=self._speaker_id,
                    provider_id=self.provider_id,
                )
            )
            self._emitted_stable = True
        if self._transport is not None and self._transport.is_connected:
            self._transport.send(audio_bytes, binary=True)

    def _do_set_language(self, language: str) -> None:
        self._language = language

    def _do_poll(self, *, timeout: float | None) -> TranscriptHypothesis | None:
        del timeout
        if self._pending:
            return self._pending.pop(0)
        return None

    def _do_finish(self) -> TranscriptHypothesis | None:
        while self._pending:
            self._record(self._pending.pop(0))
        elapsed = (time.perf_counter() - self._started_at) * 1000.0
        return TranscriptHypothesis(
            text=self._final_text,
            stability=HypothesisStability.FINAL,
            confidence=0.95,
            language=self._language,
            start_ms=0.0,
            end_ms=elapsed,
            speaker_id=self._speaker_id,
            is_final=True,
            provider_id=self.provider_id,
        )

    def _do_cancel(self) -> None:
        self._pending.clear()

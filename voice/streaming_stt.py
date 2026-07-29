# =====================================
# Titan Incremental Streaming STT
# =====================================

"""Partial / stable / final transcript stages for real-time voice (Phase 20.5/20.6).

Only stable (and final) text may reach Brain. Partial text is UI-only.
Phase 20.6 optionally drives hypotheses from a RealtimeSTTProvider.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from voice.cancellation import CancelToken
from voice.providers.realtime_stt import RealtimeSTTProvider
from voice.providers.streaming_models import HypothesisStability
from voice.speech_to_text import (
    SpeechToTextRegistry,
    TranscriptionResult,
    get_stt_registry,
    transcribe_audio,
)
from voice.stream_performance import StreamPerformanceController

logger = logging.getLogger(__name__)

StreamEmit = Callable[[str, dict[str, Any]], None]


class TranscriptStage(str, Enum):
    PARTIAL = "partial"
    STABLE = "stable"
    FINAL = "final"


@dataclass
class IncrementalTranscript:
    """Current STT view of an in-progress utterance."""

    partial_text: str = ""
    stable_text: str = ""
    final_text: str = ""
    stage: TranscriptStage = TranscriptStage.PARTIAL
    confidence: float | None = None
    provider_id: str | None = None
    language: str | None = None
    speaker_id: str | None = None
    start_ms: float | None = None
    end_ms: float | None = None
    first_partial_ms: float = 0.0
    first_stable_ms: float = 0.0
    final_ms: float = 0.0

    @property
    def brain_text(self) -> str:
        """Text safe to send to Brain — stable preferred, else final."""
        text = (self.final_text or self.stable_text or "").strip()
        return text

    @property
    def display_text(self) -> str:
        """UI-visible text (may include unstable partial)."""
        return (self.partial_text or self.stable_text or self.final_text or "").strip()

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "partial_preview": _preview(self.partial_text),
            "stable_preview": _preview(self.stable_text),
            "final_preview": _preview(self.final_text),
            "confidence": self.confidence,
            "provider_id": self.provider_id,
            "language": self.language,
            "speaker_id": self.speaker_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "first_partial_ms": round(self.first_partial_ms, 2),
            "first_stable_ms": round(self.first_stable_ms, 2),
            "final_ms": round(self.final_ms, 2),
        }


def _preview(text: str, limit: int = 80) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    return (raw[:limit] + "…") if len(raw) > limit else raw


@dataclass
class IncrementalSTTConfig:
    """Controls when partial/stable updates fire during capture."""

    partial_min_bytes: int = 3200  # ~100ms @ 16kHz PCM16 mono
    stable_min_bytes: int = 16000  # ~500ms
    retranscribe_on_stable: bool = False  # costly for batch Whisper; off by default
    mock_progressive: bool = True
    use_realtime_provider: bool = False
    coalesce_audio: bool = True


class IncrementalSTTEngine:
    """Accumulates audio and emits PARTIAL → STABLE → FINAL transcripts.

    Batch providers (Whisper) produce a true transcript only on FINAL (and
    optionally on STABLE when ``retranscribe_on_stable`` is enabled). Mock
    providers can emit progressive partials for UI latency testing.

    When ``realtime_provider`` is set (Phase 20.6), audio is forwarded to the
    provider-level stream and hypotheses drive partial/stable/final stages.
    """

    def __init__(
        self,
        *,
        locale: str = "fr-FR",
        provider_id: str = "mock",
        registry: SpeechToTextRegistry | None = None,
        config: IncrementalSTTConfig | None = None,
        emit: StreamEmit | None = None,
        cancel_token: CancelToken | None = None,
        realtime_provider: RealtimeSTTProvider | None = None,
        performance: StreamPerformanceController | None = None,
    ) -> None:
        self._locale = locale
        self._provider_id = provider_id
        self._registry = registry or get_stt_registry()
        self._config = config or IncrementalSTTConfig()
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="stt")
        self._realtime = realtime_provider
        self._performance = performance or StreamPerformanceController()
        self._buffer = bytearray()
        self._started_at = 0.0
        self._result = IncrementalTranscript()
        self._stable_emitted = False
        self._stream_started = False

    @property
    def result(self) -> IncrementalTranscript:
        return self._result

    @property
    def cancel_token(self) -> CancelToken:
        return self._cancel

    @property
    def realtime_provider(self) -> RealtimeSTTProvider | None:
        return self._realtime

    def set_realtime_provider(self, provider: RealtimeSTTProvider | None) -> None:
        self._realtime = provider
        if provider is not None:
            self._config.use_realtime_provider = True

    def set_language(self, language: str) -> None:
        self._locale = language
        self._result.language = language
        if self._realtime is not None:
            self._realtime.set_language(language)

    def reset(self) -> None:
        self._buffer.clear()
        self._started_at = 0.0
        self._result = IncrementalTranscript()
        self._stable_emitted = False
        self._stream_started = False
        self._cancel.reset()
        if self._realtime is not None:
            try:
                self._realtime.start(language=self._locale)
            except Exception as exc:
                logger.debug("Realtime STT restart on reset failed: %s", exc)

    def ingest_chunk(self, audio_bytes: bytes, *, sequence: int | None = None) -> IncrementalTranscript:
        """Append audio and optionally emit PARTIAL / STABLE updates."""
        del sequence
        if self._cancel.cancelled:
            return self._result
        if not audio_bytes:
            return self._result
        if not self._started_at:
            self._started_at = time.perf_counter()
        if not self._stream_started:
            self._stream_started = True
            self._fire("VOICE_STREAM_STARTED", {"bytes": 0})
            if self._realtime is not None and self._config.use_realtime_provider:
                self._realtime.start(language=self._locale)

        sendable = audio_bytes
        if self._config.coalesce_audio and self._realtime is not None:
            coalesced = self._performance.ingest_mic_audio(audio_bytes)
            self._buffer.extend(audio_bytes)
            if coalesced is None:
                elapsed_ms = (time.perf_counter() - self._started_at) * 1000.0
                self._performance.note_stt_event(elapsed_ms)
                return self._result
            sendable = coalesced
        else:
            self._buffer.extend(audio_bytes)

        elapsed_ms = (time.perf_counter() - self._started_at) * 1000.0
        self._performance.note_stt_event(elapsed_ms)

        if self._realtime is not None and self._config.use_realtime_provider:
            self._realtime.send_audio(sendable)
            for _ in range(8):
                hyp = self._realtime.poll(timeout=0.0)
                if hyp is None:
                    break
                self._apply_hypothesis(hyp, elapsed_ms=elapsed_ms)
            return self._result

        if len(self._buffer) >= self._config.partial_min_bytes:
            partial = self._estimate_partial()
            if partial and partial != self._result.partial_text:
                self._result.partial_text = partial
                self._result.stage = TranscriptStage.PARTIAL
                if not self._result.first_partial_ms:
                    self._result.first_partial_ms = elapsed_ms
                self._fire(
                    "VOICE_STREAM_PARTIAL",
                    {"chars": len(partial), "preview": _preview(partial)},
                )

        if (
            not self._stable_emitted
            and len(self._buffer) >= self._config.stable_min_bytes
        ):
            self.mark_stable()
        return self._result

    def mark_stable(self) -> IncrementalTranscript:
        """Promote current estimate to STABLE (still not Brain-executable alone
        until FINAL unless ``brain_text`` is taken after FINAL)."""
        if self._cancel.cancelled:
            return self._result
        if self._stable_emitted and self._result.stable_text:
            return self._result
        elapsed_ms = (
            (time.perf_counter() - self._started_at) * 1000.0 if self._started_at else 0.0
        )
        stable_text = self._result.partial_text
        if self._config.retranscribe_on_stable and self._buffer:
            try:
                transcription = self._transcribe(bytes(self._buffer))
                stable_text = (transcription.text or "").strip()
                self._result.confidence = transcription.confidence
                self._result.provider_id = transcription.provider_id
            except Exception as exc:
                logger.warning("Stable re-transcribe failed: %s", exc)
        if not stable_text:
            stable_text = self._estimate_partial()
        self._result.stable_text = stable_text
        self._result.stage = TranscriptStage.STABLE
        if not self._result.first_stable_ms:
            self._result.first_stable_ms = elapsed_ms
        self._stable_emitted = True
        self._fire(
            "VOICE_STREAM_STABLE",
            {"chars": len(stable_text), "preview": _preview(stable_text)},
        )
        return self._result

    def finalize(self, audio_bytes: bytes | None = None) -> IncrementalTranscript:
        """Run FINAL transcription — only this (or explicit stable) feeds Brain."""
        self._cancel.raise_if_cancelled()
        if audio_bytes:
            self._buffer = bytearray(audio_bytes)
        flushed = self._performance.flush_mic_audio()
        if flushed and self._realtime is not None and self._config.use_realtime_provider:
            self._realtime.send_audio(flushed)
            self._buffer.extend(flushed)
        if not self._started_at:
            self._started_at = time.perf_counter()
        if not self._stream_started:
            self._stream_started = True
            self._fire("VOICE_STREAM_STARTED", {"bytes": len(self._buffer)})
        if not self._stable_emitted and self._buffer:
            self.mark_stable()

        started = time.perf_counter()
        if self._realtime is not None and self._config.use_realtime_provider:
            hyp = self._realtime.finish()
            if hyp is not None:
                self._apply_hypothesis(
                    hyp,
                    elapsed_ms=(time.perf_counter() - self._started_at) * 1000.0,
                )
            final_text = self._result.final_text or self._result.stable_text
            self._result.stage = TranscriptStage.FINAL
            self._result.final_text = final_text
            self._result.final_ms = (time.perf_counter() - self._started_at) * 1000.0
            self._result.provider_id = (
                hyp.provider_id if hyp is not None else self._realtime.provider_id
            )
            self._fire(
                "VOICE_STREAM_FINAL",
                {
                    "chars": len(final_text or ""),
                    "stt_ms": round((time.perf_counter() - started) * 1000.0, 2),
                    "preview": _preview(final_text or ""),
                    "provider_id": self._result.provider_id,
                },
            )
            return self._result

        transcription = self._transcribe(bytes(self._buffer))
        final_text = (transcription.text or "").strip()
        elapsed_ms = (time.perf_counter() - self._started_at) * 1000.0
        self._result.final_text = final_text
        self._result.stable_text = final_text or self._result.stable_text
        self._result.partial_text = final_text or self._result.partial_text
        self._result.stage = TranscriptStage.FINAL
        self._result.confidence = transcription.confidence
        self._result.provider_id = transcription.provider_id
        self._result.final_ms = elapsed_ms
        if not self._result.first_stable_ms and final_text:
            self._result.first_stable_ms = elapsed_ms
        self._fire(
            "VOICE_STREAM_FINAL",
            {
                "chars": len(final_text),
                "stt_ms": round((time.perf_counter() - started) * 1000.0, 2),
                "preview": _preview(final_text),
            },
        )
        return self._result

    def _apply_hypothesis(self, hyp: Any, *, elapsed_ms: float) -> None:
        text = (getattr(hyp, "text", "") or "").strip()
        stability = getattr(hyp, "stability", None)
        self._result.confidence = getattr(hyp, "confidence", self._result.confidence)
        self._result.provider_id = getattr(hyp, "provider_id", self._result.provider_id)
        self._result.language = getattr(hyp, "language", self._locale)
        self._result.speaker_id = getattr(hyp, "speaker_id", self._result.speaker_id)
        self._result.start_ms = getattr(hyp, "start_ms", self._result.start_ms)
        self._result.end_ms = getattr(hyp, "end_ms", self._result.end_ms)
        if stability == HypothesisStability.PARTIAL or (
            isinstance(stability, str) and stability == "partial"
        ):
            self._result.partial_text = text
            self._result.stage = TranscriptStage.PARTIAL
            if not self._result.first_partial_ms:
                self._result.first_partial_ms = elapsed_ms
            self._fire(
                "VOICE_STREAM_PARTIAL",
                {"chars": len(text), "preview": _preview(text), "confidence": self._result.confidence},
            )
        elif stability == HypothesisStability.STABLE or (
            isinstance(stability, str) and stability == "stable"
        ):
            self._result.stable_text = text
            self._result.partial_text = text or self._result.partial_text
            self._result.stage = TranscriptStage.STABLE
            self._stable_emitted = True
            if not self._result.first_stable_ms:
                self._result.first_stable_ms = elapsed_ms
            self._fire(
                "VOICE_STREAM_STABLE",
                {"chars": len(text), "preview": _preview(text), "confidence": self._result.confidence},
            )
        else:
            self._result.final_text = text
            self._result.stable_text = text or self._result.stable_text
            self._result.partial_text = text or self._result.partial_text
            self._result.stage = TranscriptStage.FINAL
            self._result.final_ms = elapsed_ms
            if not self._result.first_stable_ms and text:
                self._result.first_stable_ms = elapsed_ms

    def _transcribe(self, audio: bytes) -> TranscriptionResult:
        self._cancel.raise_if_cancelled()
        return transcribe_audio(
            audio,
            locale=self._locale,
            provider_id=self._provider_id,
            registry=self._registry,
        )

    def _estimate_partial(self) -> str:
        """Cheap UI estimate — never used as Brain input."""
        if not self._config.mock_progressive:
            return self._result.partial_text
        # Progressive ellipsis / length hint without inventing words.
        approx_ms = max(1, len(self._buffer) // 32)
        if self._provider_id == "mock":
            # Mock: expose growing placeholder so UI/tests can assert PARTIAL.
            base = "…"
            steps = min(12, max(1, len(self._buffer) // max(1, self._config.partial_min_bytes)))
            return base * steps if steps > 1 else "…"
        return f"… ({approx_ms} ms)"

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("Incremental STT emit failed: %s", exc)

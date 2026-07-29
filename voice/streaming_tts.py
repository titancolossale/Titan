# =====================================
# Titan Streaming TTS Engine
# =====================================

"""Sentence-streamed TTS with buffer management and cancel (Phase 20.5/20.6).

Starts synthesis as soon as Brain sentence deltas are ready — does not wait
for the full assistant response when sentence_buffered mode is active.

Phase 20.6 optionally drives byte-stream chunks from a RealtimeTTSProvider.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from voice.cancellation import CancelToken
from voice.providers.realtime_tts import RealtimeTTSProvider
from voice.stream_performance import StreamPerformanceController
from voice.tts_strategy import (
    TTSStrategy,
    TTSStrategyConfig,
    TTSStrategyMode,
    clean_text_for_speech,
    select_voice_for_locale,
)

logger = logging.getLogger(__name__)

StreamEmit = Callable[[str, dict[str, Any]], None]


@dataclass
class StreamingTTSChunk:
    sequence: int
    text: str
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"
    locale: str = "fr-FR"
    voice: str = "default"

    def to_client_dict(self, session_id: str) -> dict[str, Any]:
        import base64

        return {
            "session_id": session_id,
            "sequence": self.sequence,
            "audio_base64": base64.b64encode(self.audio_bytes).decode("ascii"),
            "mime_type": self.mime_type,
            "size_bytes": len(self.audio_bytes),
            "locale": self.locale,
            "voice": self.voice,
        }


@dataclass
class StreamingTTSResult:
    chunks: list[StreamingTTSChunk] = field(default_factory=list)
    first_audio_ms: float = 0.0
    completed_ms: float = 0.0
    cancelled: bool = False
    locale: str = "fr-FR"

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "chunk_count": len(self.chunks),
            "first_audio_ms": round(self.first_audio_ms, 2),
            "completed_ms": round(self.completed_ms, 2),
            "cancelled": self.cancelled,
            "locale": self.locale,
        }


def detect_response_locale(text: str, *, default: str = "fr-FR") -> str:
    """Lightweight FR/EN switch for TTS voice selection (future multilingual)."""
    raw = (text or "").strip()
    if not raw:
        return default
    # Prefer explicit Latin patterns; keep French default for Titan product.
    en_markers = (" the ", " and ", " you ", " I ", "what's", "what is", "please")
    lowered = f" {raw.lower()} "
    en_hits = sum(1 for m in en_markers if m in lowered)
    fr_markers = (" le ", " la ", " les ", " je ", " tu ", " nous ", " vous ", " c'est ")
    fr_hits = sum(1 for m in fr_markers if m in lowered)
    if en_hits > fr_hits and en_hits >= 2:
        return "en-US"
    if fr_hits >= 1:
        return "fr-FR"
    return default


class StreamingTTSEngine:
    """Synthesize TTS from incremental Brain text with natural sentence pauses."""

    def __init__(
        self,
        strategy: TTSStrategy,
        *,
        strategy_config: TTSStrategyConfig | None = None,
        emit: StreamEmit | None = None,
        cancel_token: CancelToken | None = None,
        default_locale: str = "fr-FR",
        realtime_provider: RealtimeTTSProvider | None = None,
        performance: StreamPerformanceController | None = None,
        prefer_realtime: bool = False,
    ) -> None:
        self._strategy = strategy
        self._config = strategy_config or TTSStrategyConfig()
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="tts")
        self._default_locale = default_locale
        self._sequence = 0
        self._realtime = realtime_provider
        self._performance = performance or StreamPerformanceController()
        self._prefer_realtime = prefer_realtime

    @property
    def cancel_token(self) -> CancelToken:
        return self._cancel

    @property
    def realtime_provider(self) -> RealtimeTTSProvider | None:
        return self._realtime

    def set_realtime_provider(self, provider: RealtimeTTSProvider | None) -> None:
        self._realtime = provider
        if provider is not None:
            self._prefer_realtime = True

    def reset(self) -> None:
        self._cancel.reset()
        self._strategy.reset_cancel()
        self._sequence = 0

    def cancel(self) -> None:
        self._cancel.cancel()
        self._strategy.cancel()
        if self._realtime is not None:
            self._realtime.cancel()

    def synthesize_from_deltas(
        self,
        deltas: list[str],
        *,
        full_text: str | None = None,
        locale: str | None = None,
    ) -> StreamingTTSResult:
        """Synthesize sentence-by-sentence from deltas (or full text fallback)."""
        result = StreamingTTSResult()
        started = time.perf_counter()
        resolved_locale = locale or detect_response_locale(
            full_text or "".join(deltas), default=self._default_locale
        )
        result.locale = resolved_locale
        voice = select_voice_for_locale(
            resolved_locale,
            configured_voice=self._strategy.voice,
            config=self._config,
        )
        # Temporarily align strategy locale/voice for this utterance.
        prev_locale = self._strategy.locale
        prev_voice = self._strategy.voice
        self._strategy.locale = resolved_locale
        self._strategy.voice = voice

        self._fire("TTS_STREAM_STARTED", {"locale": resolved_locale, "voice": voice})
        try:
            if self._cancel.cancelled or self._strategy.cancelled:
                result.cancelled = True
                return result

            cleaned_full = clean_text_for_speech(
                full_text or "".join(deltas), config=self._config
            )
            if not cleaned_full:
                result.completed_ms = (time.perf_counter() - started) * 1000.0
                self._fire("TTS_STREAM_COMPLETED", result.to_safe_dict())
                return result

            if self._realtime is not None and self._prefer_realtime:
                return self._synthesize_realtime(
                    deltas=deltas,
                    cleaned_full=cleaned_full,
                    resolved_locale=resolved_locale,
                    voice=voice,
                    started=started,
                    result=result,
                )

            if self._config.mode == TTSStrategyMode.SENTENCE_BUFFERED and deltas:
                pairs = self._strategy.synthesize_streaming_deltas(deltas)
            elif self._config.mode == TTSStrategyMode.SENTENCE_BUFFERED:
                pairs = list(self._strategy.iter_sentence_audio(cleaned_full))
            else:
                full = self._strategy.synthesize_full(cleaned_full)
                pairs = [(cleaned_full, full)] if full is not None else []

            for sentence, synthesis in pairs:
                if self._cancel.cancelled or self._strategy.cancelled:
                    result.cancelled = True
                    break
                if synthesis is None:
                    continue
                if not self._performance.admit_tts_chunk(len(synthesis.audio_bytes)):
                    continue
                chunk = StreamingTTSChunk(
                    sequence=self._sequence,
                    text=sentence,
                    audio_bytes=synthesis.audio_bytes,
                    locale=resolved_locale,
                    voice=voice,
                )
                self._sequence += 1
                if not result.chunks:
                    result.first_audio_ms = (time.perf_counter() - started) * 1000.0
                result.chunks.append(chunk)
                self._performance.note_tts_event(result.first_audio_ms or 0.0)
                self._performance.release_tts_chunk(len(chunk.audio_bytes))
                self._fire(
                    "TTS_STREAM_CHUNK",
                    {
                        "sequence": chunk.sequence,
                        "chars": len(sentence),
                        "bytes": len(chunk.audio_bytes),
                    },
                )
        finally:
            self._strategy.locale = prev_locale
            self._strategy.voice = prev_voice

        result.completed_ms = (time.perf_counter() - started) * 1000.0
        self._fire(
            "TTS_STREAM_COMPLETED",
            {**result.to_safe_dict(), "cancelled": result.cancelled},
        )
        return result

    def _synthesize_realtime(
        self,
        *,
        deltas: list[str],
        cleaned_full: str,
        resolved_locale: str,
        voice: str,
        started: float,
        result: StreamingTTSResult,
    ) -> StreamingTTSResult:
        assert self._realtime is not None
        prev_locale = self._strategy.locale
        prev_voice = self._strategy.voice
        try:
            self._realtime.start(locale=resolved_locale, voice=voice)
            texts = [d for d in deltas if (d or "").strip()] or [cleaned_full]
            for text in texts:
                if self._cancel.cancelled:
                    result.cancelled = True
                    self._realtime.cancel()
                    break
                self._realtime.synthesize_incremental(text)
                for _ in range(16):
                    audio = self._realtime.poll_audio(timeout=0.0)
                    if audio is None:
                        break
                    if not self._performance.admit_tts_chunk(len(audio.audio_bytes)):
                        continue
                    chunk = StreamingTTSChunk(
                        sequence=self._sequence,
                        text=audio.text_span or text,
                        audio_bytes=audio.audio_bytes,
                        mime_type=audio.mime_type,
                        locale=resolved_locale,
                        voice=voice,
                    )
                    self._sequence += 1
                    if not result.chunks:
                        result.first_audio_ms = (time.perf_counter() - started) * 1000.0
                    result.chunks.append(chunk)
                    self._performance.note_tts_event(result.first_audio_ms or 0.0)
                    self._performance.release_tts_chunk(len(chunk.audio_bytes))
                    self._fire(
                        "TTS_STREAM_CHUNK",
                        {
                            "sequence": chunk.sequence,
                            "chars": len(chunk.text),
                            "bytes": len(chunk.audio_bytes),
                            "provider_id": self._realtime.provider_id,
                        },
                    )
            if not result.cancelled:
                for audio in self._realtime.finish():
                    if not self._performance.admit_tts_chunk(len(audio.audio_bytes)):
                        continue
                    chunk = StreamingTTSChunk(
                        sequence=self._sequence,
                        text=audio.text_span or "",
                        audio_bytes=audio.audio_bytes,
                        mime_type=audio.mime_type,
                        locale=resolved_locale,
                        voice=voice,
                    )
                    self._sequence += 1
                    if not result.chunks:
                        result.first_audio_ms = (time.perf_counter() - started) * 1000.0
                    result.chunks.append(chunk)
                    self._performance.release_tts_chunk(len(chunk.audio_bytes))
                    self._fire(
                        "TTS_STREAM_CHUNK",
                        {
                            "sequence": chunk.sequence,
                            "bytes": len(chunk.audio_bytes),
                            "provider_id": self._realtime.provider_id,
                            "final": audio.is_final,
                        },
                    )
        finally:
            self._strategy.locale = prev_locale
            self._strategy.voice = prev_voice
        result.completed_ms = (time.perf_counter() - started) * 1000.0
        self._fire(
            "TTS_STREAM_COMPLETED",
            {**result.to_safe_dict(), "cancelled": result.cancelled},
        )
        return result

    def iter_client_chunks(
        self,
        tts_result: StreamingTTSResult,
        *,
        session_id: str,
    ) -> Iterator[dict[str, Any]]:
        for chunk in tts_result.chunks:
            yield chunk.to_client_dict(session_id)

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("Streaming TTS emit failed: %s", exc)

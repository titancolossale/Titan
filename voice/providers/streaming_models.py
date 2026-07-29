# =====================================
# Titan Realtime Streaming Models
# =====================================

"""Shared models for provider-level realtime STT/TTS (Phase 20.6)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HypothesisStability(str, Enum):
    PARTIAL = "partial"
    STABLE = "stable"
    FINAL = "final"


class StreamDirection(str, Enum):
    STT = "stt"
    TTS = "tts"
    BIDIRECTIONAL = "bidirectional"


@dataclass(frozen=True)
class StreamCapabilities:
    """What a realtime provider can do."""

    provider_id: str
    direction: StreamDirection
    incremental_stt: bool = False
    incremental_tts: bool = False
    bidirectional: bool = False
    websocket: bool = False
    sse: bool = False
    http_fallback: bool = True
    partial_hypotheses: bool = False
    stable_hypotheses: bool = False
    confidence_updates: bool = False
    language_switching: bool = False
    timestamp_tracking: bool = False
    speaker_tracking: bool = False
    audio_chunks: bool = False
    provider_cancellation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "direction": self.direction.value,
            "incremental_stt": self.incremental_stt,
            "incremental_tts": self.incremental_tts,
            "bidirectional": self.bidirectional,
            "websocket": self.websocket,
            "sse": self.sse,
            "http_fallback": self.http_fallback,
            "partial_hypotheses": self.partial_hypotheses,
            "stable_hypotheses": self.stable_hypotheses,
            "confidence_updates": self.confidence_updates,
            "language_switching": self.language_switching,
            "timestamp_tracking": self.timestamp_tracking,
            "speaker_tracking": self.speaker_tracking,
            "audio_chunks": self.audio_chunks,
            "provider_cancellation": self.provider_cancellation,
        }


@dataclass
class TranscriptHypothesis:
    """One incremental STT hypothesis update."""

    text: str
    stability: HypothesisStability
    confidence: float | None = None
    language: str | None = None
    start_ms: float | None = None
    end_ms: float | None = None
    speaker_id: str | None = None
    is_final: bool = False
    provider_id: str = ""
    received_at: float = field(default_factory=time.perf_counter)

    def to_safe_dict(self) -> dict[str, Any]:
        preview = (self.text or "").strip()
        if len(preview) > 80:
            preview = preview[:80] + "…"
        return {
            "stability": self.stability.value,
            "preview": preview or None,
            "chars": len(self.text or ""),
            "confidence": self.confidence,
            "language": self.language,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "speaker_id": self.speaker_id,
            "is_final": self.is_final,
            "provider_id": self.provider_id,
        }


@dataclass
class AudioStreamChunk:
    """One incremental TTS / realtime audio chunk."""

    audio_bytes: bytes
    sequence: int
    mime_type: str = "audio/mpeg"
    sample_rate: int | None = None
    is_final: bool = False
    provider_id: str = ""
    text_span: str | None = None
    received_at: float = field(default_factory=time.perf_counter)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "bytes": len(self.audio_bytes),
            "mime_type": self.mime_type,
            "sample_rate": self.sample_rate,
            "is_final": self.is_final,
            "provider_id": self.provider_id,
            "text_span_chars": len(self.text_span) if self.text_span else 0,
        }


@dataclass
class ProviderLatencyMarks:
    """Per-provider latency slice for optimization."""

    mic_to_send_ms: float = 0.0
    provider_first_partial_ms: float = 0.0
    provider_first_stable_ms: float = 0.0
    provider_final_ms: float = 0.0
    provider_first_audio_ms: float = 0.0
    round_trip_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mic_to_send_ms": round(self.mic_to_send_ms, 2),
            "provider_first_partial_ms": round(self.provider_first_partial_ms, 2),
            "provider_first_stable_ms": round(self.provider_first_stable_ms, 2),
            "provider_final_ms": round(self.provider_final_ms, 2),
            "provider_first_audio_ms": round(self.provider_first_audio_ms, 2),
            "round_trip_ms": round(self.round_trip_ms, 2),
        }

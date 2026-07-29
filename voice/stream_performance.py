# =====================================
# Titan Stream Performance Controller
# =====================================

"""CPU / RAM / bandwidth / buffer / sync optimizations (Phase 20.6)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamPerformanceConfig:
    max_pending_audio_bytes: int = 512_000  # ~0.5 MB uplink buffer
    max_pending_tts_bytes: int = 1_024_000
    coalesce_audio_bytes: int = 3200  # ~100ms @ 16kHz PCM16 mono
    sync_skew_warn_ms: float = 250.0
    bandwidth_sample_window_seconds: float = 1.0


@dataclass
class StreamPerformanceStats:
    audio_bytes_coalesced: int = 0
    audio_chunks_dropped: int = 0
    tts_chunks_dropped: int = 0
    peak_pending_audio_bytes: int = 0
    peak_pending_tts_bytes: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    sync_skew_events: int = 0
    coalesce_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_bytes_coalesced": self.audio_bytes_coalesced,
            "audio_chunks_dropped": self.audio_chunks_dropped,
            "tts_chunks_dropped": self.tts_chunks_dropped,
            "peak_pending_audio_bytes": self.peak_pending_audio_bytes,
            "peak_pending_tts_bytes": self.peak_pending_tts_bytes,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "sync_skew_events": self.sync_skew_events,
            "coalesce_count": self.coalesce_count,
            "send_bandwidth_bps": self._bandwidth(self.bytes_sent),
            "recv_bandwidth_bps": self._bandwidth(self.bytes_received),
        }

    def _bandwidth(self, total_bytes: int) -> float:
        # Caller refreshes window externally; report lifetime average when window unset.
        return float(total_bytes)


@dataclass
class StreamPerformanceController:
    """Coalesce small audio frames, cap buffers, track bandwidth & sync skew."""

    config: StreamPerformanceConfig = field(default_factory=StreamPerformanceConfig)
    stats: StreamPerformanceStats = field(default_factory=StreamPerformanceStats)
    _audio_pending: bytearray = field(default_factory=bytearray)
    _tts_pending_bytes: int = 0
    _window_started: float = field(default_factory=time.perf_counter)
    _window_sent: int = 0
    _window_recv: int = 0
    _last_stt_ms: float | None = None
    _last_tts_ms: float | None = None

    def ingest_mic_audio(self, audio_bytes: bytes) -> bytes | None:
        """Coalesce mic frames — returns a sendable block or None if still buffering."""
        if not audio_bytes:
            return None
        if (
            len(self._audio_pending) + len(audio_bytes)
            > self.config.max_pending_audio_bytes
        ):
            # Drop oldest by clearing half the buffer — protects RAM under backpressure.
            keep = len(self._audio_pending) // 2
            del self._audio_pending[: max(0, len(self._audio_pending) - keep)]
            self.stats.audio_chunks_dropped += 1
        self._audio_pending.extend(audio_bytes)
        self.stats.peak_pending_audio_bytes = max(
            self.stats.peak_pending_audio_bytes, len(self._audio_pending)
        )
        if len(self._audio_pending) < self.config.coalesce_audio_bytes:
            return None
        out = bytes(self._audio_pending)
        self._audio_pending.clear()
        self.stats.audio_bytes_coalesced += len(out)
        self.stats.coalesce_count += 1
        self.record_sent(len(out))
        return out

    def flush_mic_audio(self) -> bytes:
        out = bytes(self._audio_pending)
        self._audio_pending.clear()
        if out:
            self.stats.audio_bytes_coalesced += len(out)
            self.record_sent(len(out))
        return out

    def admit_tts_chunk(self, size_bytes: int) -> bool:
        """Return False when TTS buffer should drop to protect RAM/bandwidth."""
        if self._tts_pending_bytes + size_bytes > self.config.max_pending_tts_bytes:
            self.stats.tts_chunks_dropped += 1
            return False
        self._tts_pending_bytes += size_bytes
        self.stats.peak_pending_tts_bytes = max(
            self.stats.peak_pending_tts_bytes, self._tts_pending_tts_safe()
        )
        self.record_received(size_bytes)
        return True

    def release_tts_chunk(self, size_bytes: int) -> None:
        self._tts_pending_bytes = max(0, self._tts_pending_bytes - size_bytes)

    def note_stt_event(self, elapsed_ms: float) -> None:
        self._last_stt_ms = elapsed_ms
        self._check_sync()

    def note_tts_event(self, elapsed_ms: float) -> None:
        self._last_tts_ms = elapsed_ms
        self._check_sync()

    def record_sent(self, size_bytes: int) -> None:
        self.stats.bytes_sent += size_bytes
        self._window_sent += size_bytes
        self._maybe_roll_window()

    def record_received(self, size_bytes: int) -> None:
        self.stats.bytes_received += size_bytes
        self._window_recv += size_bytes
        self._maybe_roll_window()

    def bandwidth_snapshot(self) -> dict[str, float]:
        elapsed = max(0.001, time.perf_counter() - self._window_started)
        return {
            "send_bps": self._window_sent / elapsed,
            "recv_bps": self._window_recv / elapsed,
            "window_seconds": elapsed,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.stats.to_dict(),
            "pending_audio_bytes": len(self._audio_pending),
            "pending_tts_bytes": self._tts_pending_bytes,
            "bandwidth": self.bandwidth_snapshot(),
        }

    def _check_sync(self) -> None:
        if self._last_stt_ms is None or self._last_tts_ms is None:
            return
        skew = abs(self._last_tts_ms - self._last_stt_ms)
        if skew > self.config.sync_skew_warn_ms:
            self.stats.sync_skew_events += 1

    def _maybe_roll_window(self) -> None:
        if (
            time.perf_counter() - self._window_started
            >= self.config.bandwidth_sample_window_seconds
        ):
            self._window_started = time.perf_counter()
            self._window_sent = 0
            self._window_recv = 0

    def _tts_pending_tts_safe(self) -> int:
        return self._tts_pending_bytes

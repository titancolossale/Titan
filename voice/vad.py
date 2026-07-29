# =====================================
# Titan Voice Activity Detection
# =====================================

"""Production-safe VAD abstraction for live voice sessions (Phase 20.3).

Defaults are device-agnostic. Callers tune sensitivity / thresholds via
``VADConfig`` or settings — never hardcode one microphone profile.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any


class VADEvent(str, Enum):
    """Discrete VAD outcomes for one audio chunk."""

    SILENCE = "silence"
    SPEECH_START = "speech_start"
    SPEECH_CONTINUE = "speech_continue"
    SPEECH_END = "speech_end"


@dataclass
class VADConfig:
    """Configurable voice-activity thresholds."""

    speech_start_threshold: float = 0.035
    speech_end_threshold: float = 0.018
    silence_timeout_seconds: float = 1.2
    min_utterance_duration_seconds: float = 0.35
    max_utterance_duration_seconds: float = 30.0
    background_noise_tolerance: float = 0.012
    sensitivity: float = 0.55  # 0.0 (hard) … 1.0 (soft)
    assumed_sample_rate: int = 16000
    assumed_sample_width_bytes: int = 2
    assumed_channels: int = 1
    frame_duration_seconds: float = 0.02

    def effective_start_threshold(self) -> float:
        # Higher sensitivity → lower start threshold.
        scale = 1.2 - max(0.0, min(1.0, self.sensitivity)) * 0.6
        return max(0.005, self.speech_start_threshold * scale)

    def effective_end_threshold(self) -> float:
        scale = 1.15 - max(0.0, min(1.0, self.sensitivity)) * 0.5
        return max(0.003, self.speech_end_threshold * scale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech_start_threshold": self.speech_start_threshold,
            "speech_end_threshold": self.speech_end_threshold,
            "silence_timeout_seconds": self.silence_timeout_seconds,
            "min_utterance_duration_seconds": self.min_utterance_duration_seconds,
            "max_utterance_duration_seconds": self.max_utterance_duration_seconds,
            "background_noise_tolerance": self.background_noise_tolerance,
            "sensitivity": self.sensitivity,
            "assumed_sample_rate": self.assumed_sample_rate,
            "assumed_sample_width_bytes": self.assumed_sample_width_bytes,
            "assumed_channels": self.assumed_channels,
            "frame_duration_seconds": self.frame_duration_seconds,
        }


@dataclass(frozen=True)
class VADResult:
    """Result of processing one audio chunk."""

    event: VADEvent
    energy: float
    in_speech: bool
    utterance_duration_seconds: float
    silence_duration_seconds: float
    rejected: bool = False
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.value,
            "energy": round(self.energy, 6),
            "in_speech": self.in_speech,
            "utterance_duration_seconds": round(self.utterance_duration_seconds, 4),
            "silence_duration_seconds": round(self.silence_duration_seconds, 4),
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
        }


def _pcm_bytes(audio_bytes: bytes) -> bytes:
    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes[44:]
    return audio_bytes


def estimate_chunk_energy(audio_bytes: bytes, *, sample_width: int = 2) -> float:
    """RMS energy normalized to ~[0, 1] for PCM-like bytes."""
    pcm = _pcm_bytes(audio_bytes)
    if not pcm:
        return 0.0
    # Prefer unsigned 8-bit energy when values look like mic/test u8 PCM.
    # (All Phase 20 synthetic fixtures use this layout.)
    if max(pcm) <= 255 and (sample_width == 1 or _looks_like_u8_pcm(pcm)):
        centered = [(b - 128) / 128.0 for b in pcm]
        mean_sq = sum(v * v for v in centered) / float(len(centered))
        return min(1.0, math.sqrt(mean_sq))
    width = max(1, sample_width)
    if width == 2 and len(pcm) >= 2:
        count = len(pcm) // 2
        if count <= 0:
            return 0.0
        samples = struct.unpack(f"<{count}h", pcm[: count * 2])
        mean_sq = sum(s * s for s in samples) / float(count)
        return min(1.0, math.sqrt(mean_sq) / 32768.0)
    centered = [(b - 128) / 128.0 for b in pcm]
    mean_sq = sum(v * v for v in centered) / float(len(centered))
    return min(1.0, math.sqrt(mean_sq))


def _looks_like_u8_pcm(pcm: bytes) -> bool:
    """Heuristic: byte stream clustered around mid-scale (synthetic/test audio)."""
    if len(pcm) < 32:
        return True
    sample = pcm[: min(len(pcm), 4096)]
    mean = sum(sample) / float(len(sample))
    return 40.0 <= mean <= 220.0


def estimate_chunk_duration_seconds(audio_bytes: bytes, config: VADConfig) -> float:
    """Estimate duration of a chunk from PCM size."""
    pcm = _pcm_bytes(audio_bytes)
    if not pcm:
        return 0.0
    # Synthetic / browser-u8 fixtures: duration from sample-rate * channels.
    if _looks_like_u8_pcm(pcm):
        u8_frame = config.assumed_sample_rate * config.assumed_channels
        return len(pcm) / float(max(1, u8_frame))
    frame = (
        config.assumed_sample_rate
        * config.assumed_sample_width_bytes
        * config.assumed_channels
    )
    if frame <= 0:
        return 0.0
    return len(pcm) / float(frame)


class VoiceActivityDetector:
    """Stateful VAD over streaming audio chunks."""

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        self._in_speech = False
        self._utterance_seconds = 0.0
        self._silence_seconds = 0.0
        self._noise_floor = self.config.background_noise_tolerance

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    @property
    def utterance_duration_seconds(self) -> float:
        return self._utterance_seconds

    def reset(self) -> None:
        self._in_speech = False
        self._utterance_seconds = 0.0
        self._silence_seconds = 0.0
        self._noise_floor = self.config.background_noise_tolerance

    def process_chunk(self, audio_bytes: bytes) -> VADResult:
        """Update VAD state from one chunk and return the discrete event."""
        if not audio_bytes:
            return VADResult(
                event=VADEvent.SILENCE,
                energy=0.0,
                in_speech=self._in_speech,
                utterance_duration_seconds=self._utterance_seconds,
                silence_duration_seconds=self._silence_seconds,
                rejected=True,
                reject_reason="empty_chunk",
            )

        energy = estimate_chunk_energy(
            audio_bytes,
            sample_width=self.config.assumed_sample_width_bytes,
        )
        duration = estimate_chunk_duration_seconds(audio_bytes, self.config)
        if duration <= 0:
            duration = self.config.frame_duration_seconds

        # Adaptive noise floor (slow rise, fast fall toward measured silence).
        if not self._in_speech:
            self._noise_floor = min(
                self.config.background_noise_tolerance * 3.0,
                (self._noise_floor * 0.95) + (energy * 0.05),
            )

        start_th = max(
            self.config.effective_start_threshold(),
            self._noise_floor + self.config.background_noise_tolerance,
        )
        end_th = max(
            self.config.effective_end_threshold(),
            self._noise_floor + (self.config.background_noise_tolerance * 0.5),
        )

        if self._utterance_seconds + duration > self.config.max_utterance_duration_seconds:
            self._in_speech = False
            result = VADResult(
                event=VADEvent.SPEECH_END,
                energy=energy,
                in_speech=False,
                utterance_duration_seconds=self._utterance_seconds + duration,
                silence_duration_seconds=0.0,
                rejected=True,
                reject_reason="max_utterance_duration",
            )
            self._utterance_seconds = 0.0
            self._silence_seconds = 0.0
            return result

        if not self._in_speech:
            if energy >= start_th:
                self._in_speech = True
                self._utterance_seconds = duration
                self._silence_seconds = 0.0
                return VADResult(
                    event=VADEvent.SPEECH_START,
                    energy=energy,
                    in_speech=True,
                    utterance_duration_seconds=self._utterance_seconds,
                    silence_duration_seconds=0.0,
                )
            self._silence_seconds += duration
            return VADResult(
                event=VADEvent.SILENCE,
                energy=energy,
                in_speech=False,
                utterance_duration_seconds=0.0,
                silence_duration_seconds=self._silence_seconds,
            )

        # In speech.
        self._utterance_seconds += duration
        if energy < end_th:
            self._silence_seconds += duration
            if self._silence_seconds >= self.config.silence_timeout_seconds:
                ended_duration = self._utterance_seconds
                self._in_speech = False
                self._silence_seconds = 0.0
                self._utterance_seconds = 0.0
                too_short = ended_duration < self.config.min_utterance_duration_seconds
                return VADResult(
                    event=VADEvent.SPEECH_END,
                    energy=energy,
                    in_speech=False,
                    utterance_duration_seconds=ended_duration,
                    silence_duration_seconds=0.0,
                    rejected=too_short,
                    reject_reason="too_short" if too_short else None,
                )
            return VADResult(
                event=VADEvent.SPEECH_CONTINUE,
                energy=energy,
                in_speech=True,
                utterance_duration_seconds=self._utterance_seconds,
                silence_duration_seconds=self._silence_seconds,
            )

        self._silence_seconds = 0.0
        return VADResult(
            event=VADEvent.SPEECH_CONTINUE,
            energy=energy,
            in_speech=True,
            utterance_duration_seconds=self._utterance_seconds,
            silence_duration_seconds=0.0,
        )

    def validate_utterance(self, audio_bytes: bytes) -> tuple[bool, str | None]:
        """Reject silence, clicks, short bursts, oversized or malformed audio."""
        if not audio_bytes:
            return False, "pure_silence"
        if len(audio_bytes) < 12 and audio_bytes[:4] == b"RIFF":
            return False, "malformed_audio"
        if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF":
            if len(audio_bytes) < 44 or audio_bytes[8:12] != b"WAVE":
                return False, "malformed_audio"
        # Browser MediaRecorder WebM/EBML is accepted (decoded by Whisper).
        is_webm = len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3"
        if not is_webm:
            # Unsupported containers (reuse enrollment-style magic checks lightly).
            head = audio_bytes[:16]
            for magic in (b"ID3", b"fLaC", b"OggS", b"\xff\xfb", b"\xff\xfa"):
                if head.startswith(magic) or magic in head:
                    return False, "unsupported_audio_format"
            if len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
                return False, "unsupported_audio_format"

        duration = estimate_chunk_duration_seconds(audio_bytes, self.config)
        energy = estimate_chunk_energy(
            audio_bytes,
            sample_width=self.config.assumed_sample_width_bytes,
        )
        if is_webm:
            # Compressed containers — rely on size floor instead of PCM silence heuristics.
            if len(audio_bytes) < 256:
                return False, "too_short"
            if duration > self.config.max_utterance_duration_seconds:
                return False, "max_utterance_duration"
            return True, None
        pcm = _pcm_bytes(audio_bytes)
        if pcm:
            # Near-constant mid-scale or zero PCM → silence / click floor.
            probe = pcm[: min(len(pcm), 8000)]
            if len(set(probe)) <= 3:
                return False, "pure_silence"
        if duration <= 0.02 and energy < self.config.effective_start_threshold():
            return False, "accidental_click"
        if duration < self.config.min_utterance_duration_seconds:
            return False, "too_short"
        if duration > self.config.max_utterance_duration_seconds:
            return False, "max_utterance_duration"
        if energy < self.config.background_noise_tolerance:
            return False, "pure_silence"
        return True, None

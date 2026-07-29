# =====================================
# Titan Microphone Calibration
# =====================================

"""Live microphone calibration for production voice UX (Phase 20.7).

Estimates noise floor, voice-activity threshold, input gain, clipping, and
low-volume conditions from short calibration windows. Never stores raw audio.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from voice.vad import VADConfig, estimate_chunk_duration_seconds, estimate_chunk_energy


@dataclass
class MicCalibrationConfig:
    """Tunable calibration thresholds (device-agnostic defaults)."""

    window_seconds: float = 1.25
    min_chunks: int = 8
    target_speech_rms: float = 0.18
    low_volume_rms: float = 0.025
    clipping_ratio_warn: float = 0.02
    clipping_peak: float = 0.98
    noise_percentile: float = 0.35
    speech_margin: float = 0.018
    max_gain: float = 4.0
    min_gain: float = 0.5
    assumed_sample_width_bytes: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_seconds": self.window_seconds,
            "min_chunks": self.min_chunks,
            "target_speech_rms": self.target_speech_rms,
            "low_volume_rms": self.low_volume_rms,
            "clipping_ratio_warn": self.clipping_ratio_warn,
            "speech_margin": self.speech_margin,
            "max_gain": self.max_gain,
            "min_gain": self.min_gain,
        }


@dataclass
class MicCalibrationSnapshot:
    """Safe calibration result for clients and diagnostics."""

    calibrated: bool = False
    noise_floor: float = 0.0
    speech_threshold: float = 0.0
    end_threshold: float = 0.0
    gain_estimate: float = 1.0
    peak_level: float = 0.0
    rms_level: float = 0.0
    clipping_ratio: float = 0.0
    clipping_detected: bool = False
    low_volume: bool = False
    sample_count: int = 0
    duration_seconds: float = 0.0
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibrated": self.calibrated,
            "noise_floor": round(self.noise_floor, 6),
            "speech_threshold": round(self.speech_threshold, 6),
            "end_threshold": round(self.end_threshold, 6),
            "gain_estimate": round(self.gain_estimate, 4),
            "peak_level": round(self.peak_level, 6),
            "rms_level": round(self.rms_level, 6),
            "clipping_ratio": round(self.clipping_ratio, 6),
            "clipping_detected": self.clipping_detected,
            "low_volume": self.low_volume,
            "sample_count": self.sample_count,
            "duration_seconds": round(self.duration_seconds, 4),
            "warning": self.warning,
        }

    def apply_to_vad_config(self, config: VADConfig) -> VADConfig:
        """Return a copy-friendly VADConfig updated from calibration."""
        if not self.calibrated:
            return config
        config.speech_start_threshold = max(0.005, self.speech_threshold)
        config.speech_end_threshold = max(0.003, self.end_threshold)
        config.background_noise_tolerance = max(0.002, self.noise_floor)
        return config


def _pcm_bytes(audio_bytes: bytes) -> bytes:
    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes[44:]
    return audio_bytes


def estimate_clipping_ratio(audio_bytes: bytes, *, sample_width: int = 2) -> float:
    """Fraction of samples near full scale (clipping heuristic)."""
    pcm = _pcm_bytes(audio_bytes)
    if not pcm:
        return 0.0
    if max(pcm) <= 255 and (sample_width == 1 or _looks_like_u8(pcm)):
        clipped = sum(1 for b in pcm if b <= 1 or b >= 254)
        return clipped / float(len(pcm))
    if sample_width == 2 and len(pcm) >= 2:
        import struct

        count = len(pcm) // 2
        samples = struct.unpack(f"<{count}h", pcm[: count * 2])
        clipped = sum(1 for s in samples if s <= -32760 or s >= 32760)
        return clipped / float(count)
    clipped = sum(1 for b in pcm if b <= 1 or b >= 254)
    return clipped / float(len(pcm))


def estimate_peak_level(audio_bytes: bytes, *, sample_width: int = 2) -> float:
    """Peak absolute amplitude normalized to ~[0, 1]."""
    pcm = _pcm_bytes(audio_bytes)
    if not pcm:
        return 0.0
    if max(pcm) <= 255 and (sample_width == 1 or _looks_like_u8(pcm)):
        peak = max(abs(b - 128) for b in pcm) / 128.0
        return min(1.0, peak)
    if sample_width == 2 and len(pcm) >= 2:
        import struct

        count = len(pcm) // 2
        samples = struct.unpack(f"<{count}h", pcm[: count * 2])
        peak = max(abs(s) for s in samples) / 32768.0
        return min(1.0, peak)
    peak = max(abs(b - 128) for b in pcm) / 128.0
    return min(1.0, peak)


def _looks_like_u8(pcm: bytes) -> bool:
    if len(pcm) < 32:
        return True
    sample = pcm[: min(len(pcm), 4096)]
    mean = sum(sample) / float(len(sample))
    return 40.0 <= mean <= 220.0


def estimate_recommended_gain(
    rms: float,
    *,
    target: float = 0.18,
    min_gain: float = 0.5,
    max_gain: float = 4.0,
) -> float:
    """Recommend a software gain multiplier toward a target speech RMS."""
    if rms <= 1e-6:
        return max_gain
    gain = target / rms
    return max(min_gain, min(max_gain, gain))


class MicCalibrator:
    """Accumulate short ambient/speech frames into a calibration snapshot."""

    def __init__(self, config: MicCalibrationConfig | None = None) -> None:
        self.config = config or MicCalibrationConfig()
        self._energies: list[float] = []
        self._peaks: list[float] = []
        self._clip_ratios: list[float] = []
        self._duration: float = 0.0
        self._started_at: float | None = None
        self._snapshot = MicCalibrationSnapshot()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def snapshot(self) -> MicCalibrationSnapshot:
        return self._snapshot

    def start(self) -> None:
        self.reset()
        self._active = True
        self._started_at = time.monotonic()

    def reset(self) -> None:
        self._energies.clear()
        self._peaks.clear()
        self._clip_ratios.clear()
        self._duration = 0.0
        self._started_at = None
        self._snapshot = MicCalibrationSnapshot()
        self._active = False

    def feed(self, audio_bytes: bytes, *, vad_config: VADConfig | None = None) -> MicCalibrationSnapshot:
        """Ingest one chunk; finalize automatically when window is complete."""
        if not self._active:
            return self._snapshot
        if not audio_bytes:
            return self._snapshot
        cfg = vad_config or VADConfig()
        energy = estimate_chunk_energy(
            audio_bytes,
            sample_width=self.config.assumed_sample_width_bytes,
        )
        peak = estimate_peak_level(
            audio_bytes,
            sample_width=self.config.assumed_sample_width_bytes,
        )
        clip = estimate_clipping_ratio(
            audio_bytes,
            sample_width=self.config.assumed_sample_width_bytes,
        )
        duration = estimate_chunk_duration_seconds(audio_bytes, cfg)
        if duration <= 0:
            duration = cfg.frame_duration_seconds
        self._energies.append(energy)
        self._peaks.append(peak)
        self._clip_ratios.append(clip)
        self._duration += duration
        if (
            self._duration >= self.config.window_seconds
            and len(self._energies) >= self.config.min_chunks
        ):
            return self.finalize()
        return self._partial_snapshot()

    def finalize(self) -> MicCalibrationSnapshot:
        """Compute calibration from collected frames."""
        self._active = False
        if not self._energies:
            self._snapshot = MicCalibrationSnapshot(
                calibrated=False,
                warning="insufficient_samples",
            )
            return self._snapshot

        sorted_e = sorted(self._energies)
        idx = max(0, min(len(sorted_e) - 1, int(len(sorted_e) * self.config.noise_percentile)))
        noise_floor = sorted_e[idx]
        rms = sum(self._energies) / float(len(self._energies))
        peak = max(self._peaks) if self._peaks else 0.0
        clip_ratio = sum(self._clip_ratios) / float(len(self._clip_ratios))
        speech_threshold = max(
            noise_floor + self.config.speech_margin,
            noise_floor * 1.35,
            0.008,
        )
        end_threshold = max(noise_floor + (self.config.speech_margin * 0.45), 0.004)
        gain = estimate_recommended_gain(
            rms,
            target=self.config.target_speech_rms,
            min_gain=self.config.min_gain,
            max_gain=self.config.max_gain,
        )
        clipping = clip_ratio >= self.config.clipping_ratio_warn or peak >= self.config.clipping_peak
        low_volume = rms < self.config.low_volume_rms and not clipping
        warning: str | None = None
        if clipping:
            warning = "clipping"
        elif low_volume:
            warning = "low_volume"

        self._snapshot = MicCalibrationSnapshot(
            calibrated=True,
            noise_floor=noise_floor,
            speech_threshold=speech_threshold,
            end_threshold=end_threshold,
            gain_estimate=gain,
            peak_level=peak,
            rms_level=rms,
            clipping_ratio=clip_ratio,
            clipping_detected=clipping,
            low_volume=low_volume,
            sample_count=len(self._energies),
            duration_seconds=self._duration,
            warning=warning,
        )
        return self._snapshot

    def _partial_snapshot(self) -> MicCalibrationSnapshot:
        if not self._energies:
            return MicCalibrationSnapshot(calibrated=False, sample_count=0)
        rms = sum(self._energies) / float(len(self._energies))
        return MicCalibrationSnapshot(
            calibrated=False,
            noise_floor=min(self._energies),
            rms_level=rms,
            peak_level=max(self._peaks) if self._peaks else 0.0,
            sample_count=len(self._energies),
            duration_seconds=self._duration,
        )


def mic_calibration_config_from_settings() -> MicCalibrationConfig:
    """Build config from ``config.settings`` with safe defaults."""
    try:
        from config import settings as app_settings
    except Exception:
        return MicCalibrationConfig()
    return MicCalibrationConfig(
        window_seconds=float(
            getattr(app_settings, "TITAN_VOICE_MIC_CALIBRATION_SECONDS", 1.25)
        ),
        low_volume_rms=float(
            getattr(app_settings, "TITAN_VOICE_MIC_LOW_VOLUME_RMS", 0.025)
        ),
        clipping_ratio_warn=float(
            getattr(app_settings, "TITAN_VOICE_MIC_CLIPPING_RATIO", 0.02)
        ),
        target_speech_rms=float(
            getattr(app_settings, "TITAN_VOICE_MIC_TARGET_RMS", 0.18)
        ),
    )

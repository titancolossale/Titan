# =====================================
# Titan Voice Sample Validator
# =====================================

"""Quality gates for enrollment audio samples (Phase 20.2)."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

from voice.enrollment_models import (
    EnrollmentConfig,
    SampleRejectReason,
    SampleValidationResult,
)
from voice.speaker_identifier import extract_voice_features


# Known unsupported container signatures (not WAV/PCM enrollment audio).
_UNSUPPORTED_MAGIC = (
    b"ID3",  # mp3 tags
    b"fLaC",
    b"OggS",
    b"\xff\xfb",  # mp3 frame
    b"\xff\xfa",
    b"ftyp",  # m4a/mp4 (often offset 4)
)


def _pcm_bytes(audio_bytes: bytes) -> bytes:
    """Strip a standard WAV header when present; otherwise return raw bytes."""
    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes[44:]
    return audio_bytes


def _is_corrupted_wav(audio_bytes: bytes) -> bool:
    if len(audio_bytes) < 12:
        return False
    if audio_bytes[:4] != b"RIFF":
        return False
    if len(audio_bytes) < 44:
        return True
    if audio_bytes[8:12] != b"WAVE":
        return True
    return False


def _is_unsupported(audio_bytes: bytes) -> bool:
    if not audio_bytes:
        return False
    head = audio_bytes[:12]
    for magic in _UNSUPPORTED_MAGIC:
        if head.startswith(magic) or magic in audio_bytes[:16]:
            return True
    # MP4/M4A often has 'ftyp' at offset 4.
    if len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
        return True
    return False


def estimate_duration_seconds(
    audio_bytes: bytes,
    *,
    config: EnrollmentConfig,
) -> float:
    """Estimate duration from WAV header or assumed PCM layout."""
    if not audio_bytes:
        return 0.0
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        # Try fmt chunk sample rate + channels + bits.
        try:
            channels = struct.unpack_from("<H", audio_bytes, 22)[0]
            sample_rate = struct.unpack_from("<I", audio_bytes, 24)[0]
            bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]
            pcm = _pcm_bytes(audio_bytes)
            byte_rate = max(1, channels * max(1, bits_per_sample // 8) * max(1, sample_rate))
            return len(pcm) / float(byte_rate)
        except struct.error:
            pass
    frame = (
        config.assumed_sample_rate
        * config.assumed_sample_width_bytes
        * config.assumed_channels
    )
    return len(_pcm_bytes(audio_bytes)) / float(max(1, frame))


def feature_fingerprint(embedding: Iterable[float]) -> str:
    """Stable short fingerprint of an embedding (not reversible to audio)."""
    rounded = ",".join(f"{float(v):.5f}" for v in embedding)
    return hashlib.sha256(rounded.encode("utf-8")).hexdigest()[:24]


def _silence_ratio(pcm: bytes) -> float:
    if not pcm:
        return 1.0
    silent = 0
    for value in pcm:
        if value < 8 or value > 247 or 120 <= value <= 136:
            silent += 1
    return silent / float(len(pcm))


def _clipping_ratio(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    clipped = sum(1 for value in pcm if value <= 1 or value >= 254)
    return clipped / float(len(pcm))


def _energy_variance(pcm: bytes, chunks: int = 8) -> float:
    if len(pcm) < chunks:
        return 0.0
    size = len(pcm) // chunks
    energies: list[float] = []
    for index in range(chunks):
        start = index * size
        end = start + size if index < chunks - 1 else len(pcm)
        block = pcm[start:end] or b"\x00"
        mean = sum(block) / len(block)
        energy = sum((b - mean) ** 2 for b in block) / len(block)
        energies.append(math.sqrt(energy))
    mean_e = sum(energies) / len(energies)
    return sum((e - mean_e) ** 2 for e in energies) / len(energies)


def _mean_split_delta(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    half = len(pcm) // 2
    mean_a = sum(pcm[:half]) / float(half)
    mean_b = sum(pcm[half:]) / float(max(1, len(pcm) - half))
    return abs(mean_a - mean_b)


def _quality_score(
    *,
    silence_ratio: float,
    clipping_ratio: float,
    duration: float,
    config: EnrollmentConfig,
    energy_var: float,
) -> float:
    duration_factor = min(1.0, duration / max(config.min_sample_duration_seconds, 0.1))
    silence_factor = max(0.0, 1.0 - silence_ratio)
    clipping_factor = max(0.0, 1.0 - clipping_ratio * 4.0)
    # Mild energy variance is healthy speech; extreme spikes hint multi-talker/noise.
    variance_factor = 1.0
    if energy_var > 2500:
        variance_factor = 0.35
    elif energy_var > 900:
        variance_factor = 0.7
    score = 0.35 * duration_factor + 0.35 * silence_factor + 0.2 * clipping_factor
    score += 0.1 * variance_factor
    return max(0.0, min(1.0, score))


def validate_enrollment_sample(
    audio_bytes: bytes,
    *,
    config: EnrollmentConfig | None = None,
    existing_fingerprints: Iterable[str] | None = None,
) -> SampleValidationResult:
    """Validate one enrollment sample; never logs or retains raw audio."""
    cfg = config or EnrollmentConfig()
    if not audio_bytes:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=0.0,
            reason="Audio vide",
            reject_code=SampleRejectReason.EMPTY,
        )
    if _is_corrupted_wav(audio_bytes):
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=0.0,
            reason="Fichier audio WAV corrompu",
            reject_code=SampleRejectReason.CORRUPTED,
        )
    if _is_unsupported(audio_bytes):
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=0.0,
            reason="Format audio non supporté pour l'enrollment",
            reject_code=SampleRejectReason.UNSUPPORTED,
        )

    duration = estimate_duration_seconds(audio_bytes, config=cfg)
    if duration < cfg.min_sample_duration_seconds:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=duration,
            reason="Échantillon trop court",
            reject_code=SampleRejectReason.TOO_SHORT,
        )
    if duration > cfg.max_sample_duration_seconds:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=duration,
            reason="Échantillon trop long",
            reject_code=SampleRejectReason.TOO_LONG,
        )

    pcm = _pcm_bytes(audio_bytes)
    if not pcm:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=duration,
            reason="Audio vide après décodage",
            reject_code=SampleRejectReason.EMPTY,
        )

    silence = _silence_ratio(pcm)
    clipping = _clipping_ratio(pcm)
    # Clipping is checked before silence so saturated signals are not
    # mislabeled as silence (extremes also inflate the silence heuristic).
    if clipping >= 0.35:
        return SampleValidationResult(
            accepted=False,
            quality_score=max(0.0, 1.0 - clipping),
            duration_seconds=duration,
            reason="Saturation audio sévère",
            reject_code=SampleRejectReason.SEVERE_CLIPPING,
        )
    if silence >= 0.92:
        return SampleValidationResult(
            accepted=False,
            quality_score=max(0.0, 1.0 - silence),
            duration_seconds=duration,
            reason="Silence excessif",
            reject_code=SampleRejectReason.EXCESSIVE_SILENCE,
        )

    energy_var = _energy_variance(pcm)
    mean_split = _mean_split_delta(pcm)
    # Large first/second-half mean gap ≈ overlapping talkers / mixed sources.
    if mean_split >= 80.0 or energy_var >= 4000:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.2,
            duration_seconds=duration,
            reason="Plusieurs locuteurs détectés",
            reject_code=SampleRejectReason.MULTI_SPEAKER,
        )

    embedding = extract_voice_features(audio_bytes)
    fingerprint = feature_fingerprint(embedding)
    existing = set(existing_fingerprints or [])

    from voice.enrollment_quality import analyze_production_quality

    production = analyze_production_quality(
        audio_bytes,
        config=cfg,
        existing_fingerprints=existing,
        feature_fingerprint=fingerprint,
    )

    if fingerprint in existing:
        return SampleValidationResult(
            accepted=False,
            quality_score=0.0,
            duration_seconds=duration,
            reason="Échantillon dupliqué",
            reject_code=SampleRejectReason.DUPLICATE,
            feature_fingerprint=fingerprint,
            production_metrics=production.to_dict(),
        )

    quality = _quality_score(
        silence_ratio=silence,
        clipping_ratio=clipping,
        duration=duration,
        config=cfg,
        energy_var=energy_var,
    )
    # Production metrics are always attached. Hard-reject only when classic
    # quality already fails *and* production metrics confirm a specific gate
    # (avoids rejecting valid low-variance synthetic / quiet speech that
    # still clears silence/clipping/duration gates).
    if quality < cfg.min_quality_score:
        if production.microphone_quality < 0.35:
            return SampleValidationResult(
                accepted=False,
                quality_score=min(quality, production.microphone_quality),
                duration_seconds=duration,
                reason="Qualité microphone insuffisante",
                reject_code=SampleRejectReason.POOR_MICROPHONE,
                feature_fingerprint=fingerprint,
                production_metrics=production.to_dict(),
            )
        if production.signal_level < 0.05:
            return SampleValidationResult(
                accepted=False,
                quality_score=min(quality, production.overall_score),
                duration_seconds=duration,
                reason="Niveau de signal trop faible",
                reject_code=SampleRejectReason.LOW_SIGNAL,
                feature_fingerprint=fingerprint,
                production_metrics=production.to_dict(),
            )
        if production.background_noise >= 0.92:
            return SampleValidationResult(
                accepted=False,
                quality_score=min(quality, production.overall_score),
                duration_seconds=duration,
                reason="Bruit de fond excessif",
                reject_code=SampleRejectReason.HIGH_NOISE,
                feature_fingerprint=fingerprint,
                production_metrics=production.to_dict(),
            )
        return SampleValidationResult(
            accepted=False,
            quality_score=quality,
            duration_seconds=duration,
            reason="Qualité audio insuffisante",
            reject_code=SampleRejectReason.LOW_QUALITY,
            feature_fingerprint=fingerprint,
            production_metrics=production.to_dict(),
        )

    return SampleValidationResult(
        accepted=True,
        quality_score=quality,
        duration_seconds=duration,
        reason=None,
        reject_code=None,
        feature_fingerprint=fingerprint,
        production_metrics=production.to_dict(),
    )

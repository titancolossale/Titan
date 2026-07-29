# =====================================
# Titan Enrollment Quality & Duplicate Guards
# =====================================

"""Enrollment quality scoring, duplicate detection, language independence
(Phase 20.8 + production metrics Phase 20.10A).

Does not collect real Nolan/Ibrahim voices — preparation only. Features remain
acoustic (language-independent). Cross-user near-duplicate detection prevents
identity confusion before activation.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Any, Iterable

from voice.embedding_provider import (
    cosine_similarity,
    embeddings_compatible,
    get_embedding_provider,
    mean_embedding,
)
from voice.enrollment_models import EMBEDDING_VERSION, EnrollmentConfig, SpeakerIdentityProfile


@dataclass(frozen=True)
class EmbeddingQualityReport:
    score: float
    dimension: int
    embedding_version: str
    language_independent: bool = True
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "dimension": self.dimension,
            "embedding_version": self.embedding_version,
            "language_independent": self.language_independent,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DuplicateMatch:
    other_user_id: str
    other_profile_id: str
    similarity: float
    embedding_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "other_user_id": self.other_user_id,
            "other_profile_id": self.other_profile_id,
            "similarity": round(self.similarity, 4),
            "embedding_version": self.embedding_version,
        }


@dataclass(frozen=True)
class DuplicateDetectionResult:
    is_duplicate: bool
    matches: tuple[DuplicateMatch, ...] = ()
    threshold: float = 0.92

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "threshold": self.threshold,
            "matches": [m.to_dict() for m in self.matches],
        }


def score_embedding_quality(
    embedding: Iterable[float],
    *,
    embedding_version: str | None = None,
) -> EmbeddingQualityReport:
    provider = get_embedding_provider()
    version = embedding_version or provider.embedding_version
    values = [float(v) for v in embedding]
    score = provider.quality_score(values)
    notes: list[str] = []
    if score < 0.25:
        notes.append("low_information_embedding")
    if len(values) != provider.dimension:
        notes.append("dimension_mismatch")
        score = min(score, 0.1)
    if not embeddings_compatible(version, provider.embedding_version):
        notes.append("embedding_version_mismatch")
        score = 0.0
    return EmbeddingQualityReport(
        score=score,
        dimension=len(values),
        embedding_version=version,
        language_independent=True,
        notes=tuple(notes),
    )


def detect_cross_user_duplicates(
    *,
    user_id: str,
    embeddings: list[list[float]],
    candidates: list[SpeakerIdentityProfile],
    embedding_version: str = EMBEDDING_VERSION,
    threshold: float = 0.92,
) -> DuplicateDetectionResult:
    """Flag near-identical voiceprints belonging to a different user."""
    probe = mean_embedding(embeddings)
    if not probe:
        return DuplicateDetectionResult(is_duplicate=False, threshold=threshold)
    matches: list[DuplicateMatch] = []
    for profile in candidates:
        if profile.user_id == user_id:
            continue
        if not profile.active:
            continue
        if not embeddings_compatible(embedding_version, profile.embedding_version):
            continue
        other = mean_embedding(profile.embeddings)
        if not other:
            continue
        sim = cosine_similarity(probe, other)
        if sim >= threshold:
            matches.append(
                DuplicateMatch(
                    other_user_id=profile.user_id,
                    other_profile_id=profile.profile_id,
                    similarity=sim,
                    embedding_version=profile.embedding_version,
                )
            )
    matches.sort(key=lambda m: m.similarity, reverse=True)
    return DuplicateDetectionResult(
        is_duplicate=bool(matches),
        matches=tuple(matches),
        threshold=threshold,
    )


def language_independence_score(
    embeddings_a: list[list[float]],
    embeddings_b: list[list[float]],
) -> float:
    """Similarity between two phrase-sets for the same speaker (FR vs EN, etc.).

    High score indicates language-independent enrollment features.
    """
    a = mean_embedding(embeddings_a)
    b = mean_embedding(embeddings_b)
    if not a or not b:
        return 0.0
    return round(cosine_similarity(a, b), 4)


def safe_profile_replacement_plan(
    *,
    existing_profile_id: str | None,
    new_profile_id: str,
    replace_existing: bool,
) -> dict[str, Any]:
    """Declarative safe-replace plan — never silently overwrite without consent."""
    if existing_profile_id and not replace_existing:
        return {
            "action": "blocked",
            "reason": "active_profile_exists",
            "existing_profile_id": existing_profile_id,
            "new_profile_id": new_profile_id,
        }
    if existing_profile_id:
        return {
            "action": "atomic_replace",
            "existing_profile_id": existing_profile_id,
            "new_profile_id": new_profile_id,
            "revoke_old": True,
        }
    return {
        "action": "activate_new",
        "existing_profile_id": None,
        "new_profile_id": new_profile_id,
        "revoke_old": False,
    }


@dataclass(frozen=True)
class SessionQualityReport:
    """Aggregate enrollment-session quality (samples + embeddings)."""

    sample_quality_avg: float
    embedding_quality_avg: float
    aggregate_score: float
    sample_count: int
    ready_to_finish: bool
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_quality_avg": round(self.sample_quality_avg, 4),
            "embedding_quality_avg": round(self.embedding_quality_avg, 4),
            "aggregate_score": round(self.aggregate_score, 4),
            "sample_count": self.sample_count,
            "ready_to_finish": self.ready_to_finish,
            "notes": list(self.notes),
        }


def score_session_quality(
    *,
    sample_scores: list[float],
    embeddings: list[list[float]],
    required_samples: int,
    embedding_version: str | None = None,
) -> SessionQualityReport:
    """Combine sample + embedding quality into one enrollment readiness score."""
    notes: list[str] = []
    sample_avg = (
        sum(sample_scores) / len(sample_scores) if sample_scores else 0.0
    )
    emb_reports = [
        score_embedding_quality(emb, embedding_version=embedding_version)
        for emb in embeddings
    ]
    emb_avg = (
        sum(r.score for r in emb_reports) / len(emb_reports) if emb_reports else 0.0
    )
    for report in emb_reports:
        notes.extend(report.notes)
    aggregate = (sample_avg * 0.55) + (emb_avg * 0.45) if sample_scores else 0.0
    if len(sample_scores) < required_samples:
        notes.append("insufficient_samples")
    if sample_avg < 0.45:
        notes.append("low_sample_quality")
    # Deduplicate notes while preserving order.
    seen: set[str] = set()
    unique_notes: list[str] = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            unique_notes.append(note)
    return SessionQualityReport(
        sample_quality_avg=sample_avg,
        embedding_quality_avg=emb_avg,
        aggregate_score=aggregate,
        sample_count=len(sample_scores),
        ready_to_finish=len(sample_scores) >= required_samples,
        notes=tuple(unique_notes),
    )


def detect_same_user_near_duplicate(
    *,
    embeddings: list[list[float]],
    existing_profile: SpeakerIdentityProfile | None,
    embedding_version: str = EMBEDDING_VERSION,
    threshold: float = 0.97,
) -> DuplicateDetectionResult:
    """Detect near-identical re-enrollment against the user's current profile.

    High similarity with replace_existing=True is expected (update path).
    Without replace intent, callers may treat this as a no-op update warning.
    """
    if existing_profile is None or not existing_profile.embeddings:
        return DuplicateDetectionResult(is_duplicate=False, threshold=threshold)
    if not embeddings_compatible(embedding_version, existing_profile.embedding_version):
        return DuplicateDetectionResult(is_duplicate=False, threshold=threshold)
    probe = mean_embedding(embeddings)
    other = mean_embedding(existing_profile.embeddings)
    if not probe or not other:
        return DuplicateDetectionResult(is_duplicate=False, threshold=threshold)
    sim = cosine_similarity(probe, other)
    if sim < threshold:
        return DuplicateDetectionResult(is_duplicate=False, threshold=threshold)
    match = DuplicateMatch(
        other_user_id=existing_profile.user_id,
        other_profile_id=existing_profile.profile_id,
        similarity=sim,
        embedding_version=existing_profile.embedding_version,
    )
    return DuplicateDetectionResult(
        is_duplicate=True,
        matches=(match,),
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Phase 20.10A — production sample quality metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionQualityMetrics:
    """Detailed quality gates for production enrollment samples."""

    signal_level: float
    background_noise: float
    speech_duration_seconds: float
    language_independence: bool
    duplicate_recording: bool
    clipping_ratio: float
    microphone_quality: float
    overall_score: float
    passed: bool
    reject_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_level": round(self.signal_level, 4),
            "background_noise": round(self.background_noise, 4),
            "speech_duration_seconds": round(self.speech_duration_seconds, 4),
            "language_independence": self.language_independence,
            "duplicate_recording": self.duplicate_recording,
            "clipping_ratio": round(self.clipping_ratio, 4),
            "microphone_quality": round(self.microphone_quality, 4),
            "overall_score": round(self.overall_score, 4),
            "passed": self.passed,
            "reject_reasons": list(self.reject_reasons),
        }


def _pcm_bytes(audio_bytes: bytes) -> bytes:
    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes[44:]
    return audio_bytes


def _estimate_duration(audio_bytes: bytes, config: EnrollmentConfig) -> float:
    if not audio_bytes:
        return 0.0
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        try:
            channels = struct.unpack_from("<H", audio_bytes, 22)[0]
            sample_rate = struct.unpack_from("<I", audio_bytes, 24)[0]
            bits = struct.unpack_from("<H", audio_bytes, 34)[0]
            pcm = _pcm_bytes(audio_bytes)
            byte_rate = max(1, channels * max(1, bits // 8) * max(1, sample_rate))
            return len(pcm) / float(byte_rate)
        except struct.error:
            pass
    frame = (
        config.assumed_sample_rate
        * config.assumed_sample_width_bytes
        * config.assumed_channels
    )
    return len(_pcm_bytes(audio_bytes)) / float(max(1, frame))


def analyze_production_quality(
    audio_bytes: bytes,
    *,
    config: EnrollmentConfig | None = None,
    existing_fingerprints: Iterable[str] | None = None,
    feature_fingerprint: str | None = None,
) -> ProductionQualityMetrics:
    """Validate signal, noise, duration, clipping, mic quality, duplicates.

    Language independence is a property of the embedding pipeline (acoustic
    features), not of the spoken language of this clip — always True when the
    active provider is available.
    """
    cfg = config or EnrollmentConfig()
    reasons: list[str] = []
    pcm = _pcm_bytes(audio_bytes) if audio_bytes else b""
    duration = _estimate_duration(audio_bytes, cfg)

    if not pcm:
        return ProductionQualityMetrics(
            signal_level=0.0,
            background_noise=1.0,
            speech_duration_seconds=0.0,
            language_independence=True,
            duplicate_recording=False,
            clipping_ratio=0.0,
            microphone_quality=0.0,
            overall_score=0.0,
            passed=False,
            reject_reasons=("empty_audio",),
        )

    # Signal / noise heuristics from byte energy.
    mean = sum(pcm) / len(pcm)
    variance = sum((b - mean) ** 2 for b in pcm) / len(pcm)
    rms = math.sqrt(variance) / 128.0
    signal_level = max(0.0, min(1.0, rms))

    quiet = sum(1 for b in pcm if abs(b - 128) < 8 or b < 12 or b > 243)
    background_noise = quiet / float(len(pcm))
    # Invert: high quiet-ratio with mid energy ≈ noise floor dominance.
    if signal_level < 0.08:
        background_noise = max(background_noise, 0.85)

    clipped = sum(1 for b in pcm if b <= 1 or b >= 254)
    clipping_ratio = clipped / float(len(pcm))

    # Microphone quality: combines signal headroom, low clipping, usable duration.
    duration_factor = min(1.0, duration / max(cfg.min_sample_duration_seconds, 0.1))
    clip_factor = max(0.0, 1.0 - clipping_ratio * 5.0)
    noise_factor = max(0.0, 1.0 - background_noise)
    mic_quality = (
        0.35 * signal_level + 0.25 * clip_factor + 0.2 * noise_factor + 0.2 * duration_factor
    )
    mic_quality = max(0.0, min(1.0, mic_quality))

    duplicate = False
    if feature_fingerprint and existing_fingerprints:
        duplicate = feature_fingerprint in set(existing_fingerprints)

    provider = get_embedding_provider()
    language_independent = bool(provider.is_available)

    if duration < cfg.min_sample_duration_seconds:
        reasons.append("speech_duration_too_short")
    if duration > cfg.max_sample_duration_seconds:
        reasons.append("speech_duration_too_long")
    if signal_level < 0.05:
        reasons.append("signal_level_too_low")
    if background_noise >= 0.92:
        reasons.append("background_noise_excessive")
    if clipping_ratio >= 0.35:
        reasons.append("severe_clipping")
    if mic_quality < 0.35:
        reasons.append("microphone_quality_low")
    if duplicate:
        reasons.append("duplicate_recording")

    overall = (
        0.25 * signal_level
        + 0.2 * noise_factor
        + 0.2 * duration_factor
        + 0.2 * clip_factor
        + 0.15 * mic_quality
    )
    if duplicate:
        overall = 0.0
    passed = not reasons and overall >= cfg.min_quality_score

    return ProductionQualityMetrics(
        signal_level=signal_level,
        background_noise=background_noise,
        speech_duration_seconds=duration,
        language_independence=language_independent,
        duplicate_recording=duplicate,
        clipping_ratio=clipping_ratio,
        microphone_quality=mic_quality,
        overall_score=overall,
        passed=passed,
        reject_reasons=tuple(reasons),
    )

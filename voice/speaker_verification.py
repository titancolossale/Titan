# =====================================
# Titan Speaker Verification Engine
# =====================================

"""Production-oriented speaker verification (Phase 20.11).

Supports cosine / provider-appropriate similarity, configurable thresholds,
UNKNOWN / AMBIGUOUS outcomes, confidence scoring, multi-sample aggregation,
and rejection when confidence is insufficient.

Titan must prefer UNKNOWN over incorrectly identifying a speaker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from voice.embedding_provider import (
    BaseEmbeddingProvider,
    cosine_similarity,
    embeddings_compatible,
    get_embedding_provider,
    is_dev_fallback_version,
    mean_embedding,
)
from voice.enrollment_models import RecognitionBand, VerificationOutcome


def default_verification_config() -> VerificationConfig:
    """Build VerificationConfig from env / biometric trust mode."""
    from voice.biometric_trust import production_verification_defaults

    defaults = production_verification_defaults()
    try:
        from config import settings

        high = float(
            getattr(settings, "TITAN_VOICE_SPEAKER_MIN_CONFIDENCE", 0.72)
        )
        medium = float(
            getattr(settings, "TITAN_VOICE_SPEAKER_MEDIUM_CONFIDENCE", 0.55)
        )
        delta = float(
            getattr(settings, "TITAN_VOICE_SPEAKER_AMBIGUITY_DELTA", 0.05)
        )
        aggregation = str(
            getattr(settings, "TITAN_VOICE_EMBEDDING_AGGREGATION", "max_centroid")
        )
        require_trust = bool(
            getattr(
                settings,
                "TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST",
                defaults["require_production_trust"],
            )
        )
        allow_dev = bool(
            getattr(
                settings,
                "TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY",
                defaults["allow_dev_fallback_identity"],
            )
        )
        # Production trust mode forces strict defaults unless explicitly overridden
        # via env that already set the settings flags.
        mode_defaults = defaults
        if mode_defaults["require_production_trust"]:
            require_trust = True
        if not mode_defaults["allow_dev_fallback_identity"]:
            allow_dev = False
    except Exception:
        high, medium, delta = 0.72, 0.55, 0.05
        aggregation = "max_centroid"
        require_trust = defaults["require_production_trust"]
        allow_dev = defaults["allow_dev_fallback_identity"]
    return VerificationConfig(
        high_threshold=high,
        medium_threshold=medium,
        ambiguity_delta=delta,
        require_production_trust=require_trust,
        allow_dev_fallback_identity=allow_dev,
        aggregation=aggregation,
    )


class VerificationDecision(str, Enum):
    """Runtime verification decision (prefer UNKNOWN over false identity)."""

    VERIFIED = "verified"
    MATCHED = "matched"  # backward-compatible alias of VERIFIED
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"
    VERSION_MISMATCH = "version_mismatch"
    UNTRUSTED_BACKEND = "untrusted_backend"


@dataclass(frozen=True)
class VerificationConfig:
    """Configurable verification thresholds."""

    high_threshold: float = 0.72
    medium_threshold: float = 0.55
    ambiguity_delta: float = 0.05
    require_production_trust: bool = False
    allow_dev_fallback_identity: bool = True
    aggregation: str = "max_centroid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "high_threshold": self.high_threshold,
            "medium_threshold": self.medium_threshold,
            "ambiguity_delta": self.ambiguity_delta,
            "require_production_trust": self.require_production_trust,
            "allow_dev_fallback_identity": self.allow_dev_fallback_identity,
            "aggregation": self.aggregation,
        }


@dataclass(frozen=True)
class SpeakerScore:
    """Per-user similarity score against enrolled embeddings."""

    user_id: str
    score: float
    sample_scores: tuple[float, ...]
    centroid_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "score": round(self.score, 4),
            "sample_count": len(self.sample_scores),
            "centroid_score": (
                round(self.centroid_score, 4)
                if self.centroid_score is not None
                else None
            ),
        }


@dataclass(frozen=True)
class SpeakerVerificationResult:
    """Safe verification outcome — never includes raw embeddings."""

    decision: VerificationDecision
    outcome: VerificationOutcome
    recognition_band: RecognitionBand
    confidence: float
    threshold: float
    matched_user: str | None
    reason: str
    embedding_version: str
    production_trusted: bool
    scores: tuple[SpeakerScore, ...] = ()
    second_best_user: str | None = None
    second_best_score: float | None = None

    @property
    def is_known(self) -> bool:
        return (
            self.decision
            in {VerificationDecision.MATCHED, VerificationDecision.VERIFIED}
            and self.matched_user is not None
        )

    @property
    def is_verified(self) -> bool:
        return self.is_known and self.decision in {
            VerificationDecision.MATCHED,
            VerificationDecision.VERIFIED,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "outcome": self.outcome.value,
            "recognition_band": self.recognition_band.value,
            "confidence": round(self.confidence, 4),
            "threshold": round(self.threshold, 4),
            "matched_user": self.matched_user,
            "reason": self.reason,
            "embedding_version": self.embedding_version,
            "production_trusted": self.production_trusted,
            "is_known": self.is_known,
            "second_best_user": self.second_best_user,
            "second_best_score": (
                round(self.second_best_score, 4)
                if self.second_best_score is not None
                else None
            ),
            "scores": [s.to_dict() for s in self.scores],
        }


class SpeakerVerificationEngine:
    """Score a probe embedding against enrolled multi-sample profiles."""

    def __init__(
        self,
        config: VerificationConfig | None = None,
        *,
        provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self._config = config or VerificationConfig()
        self._provider = provider

    @property
    def config(self) -> VerificationConfig:
        return self._config

    def _provider_or_default(self) -> BaseEmbeddingProvider:
        return self._provider or get_embedding_provider()

    def score_user(
        self,
        probe: Iterable[float],
        profile_embeddings: list[list[float]],
        *,
        user_id: str,
    ) -> SpeakerScore:
        """Aggregate similarity across multiple enrollment embeddings."""
        probe_vec = [float(v) for v in probe]
        sample_scores: list[float] = []
        provider = self._provider_or_default()
        for emb in profile_embeddings:
            if not emb:
                continue
            sample_scores.append(provider.similarity(probe_vec, list(emb)))
        centroid = mean_embedding([list(e) for e in profile_embeddings if e])
        centroid_score: float | None = None
        if centroid:
            centroid_score = provider.similarity(probe_vec, centroid)
        if not sample_scores and centroid_score is None:
            return SpeakerScore(
                user_id=user_id,
                score=0.0,
                sample_scores=(),
                centroid_score=None,
            )
        best_sample = max(sample_scores) if sample_scores else 0.0
        if self._config.aggregation in {"mean", "centroid"}:
            score = centroid_score if centroid_score is not None else best_sample
        else:
            # max_centroid: take the stronger of max-vs-samples and centroid.
            score = best_sample
            if centroid_score is not None:
                score = max(score, centroid_score)
        return SpeakerScore(
            user_id=user_id,
            score=score,
            sample_scores=tuple(sample_scores),
            centroid_score=centroid_score,
        )

    def verify(
        self,
        *,
        probe_embedding: Iterable[float],
        enrolled: dict[str, list[list[float]]],
        profile_versions: dict[str, str] | None = None,
        expected_user_id: str | None = None,
    ) -> SpeakerVerificationResult:
        """Verify probe against enrolled users — prefer UNKNOWN over false ID."""
        provider = self._provider_or_default()
        version = provider.embedding_version
        production_trusted = provider.is_production_trusted
        threshold = self._config.high_threshold
        probe = [float(v) for v in probe_embedding]

        if self._config.require_production_trust and not production_trusted:
            return SpeakerVerificationResult(
                decision=VerificationDecision.UNTRUSTED_BACKEND,
                outcome=VerificationOutcome.FAILED,
                recognition_band=RecognitionBand.INACTIVE,
                confidence=0.0,
                threshold=threshold,
                matched_user=None,
                reason="production_trust_required",
                embedding_version=version,
                production_trusted=False,
            )

        if (
            not self._config.allow_dev_fallback_identity
            and is_dev_fallback_version(version)
        ):
            return SpeakerVerificationResult(
                decision=VerificationDecision.UNTRUSTED_BACKEND,
                outcome=VerificationOutcome.UNKNOWN,
                recognition_band=RecognitionBand.LOW,
                confidence=0.0,
                threshold=threshold,
                matched_user=None,
                reason="dev_fallback_identity_disabled",
                embedding_version=version,
                production_trusted=False,
            )

        if not probe or not enrolled:
            return SpeakerVerificationResult(
                decision=VerificationDecision.UNKNOWN,
                outcome=VerificationOutcome.UNKNOWN,
                recognition_band=RecognitionBand.LOW,
                confidence=0.0,
                threshold=threshold,
                matched_user=None,
                reason="missing_embeddings" if not probe else "no_enrolled_profiles",
                embedding_version=version,
                production_trusted=production_trusted,
            )

        scores: list[SpeakerScore] = []
        versions = profile_versions or {}
        for user_id, embeddings in enrolled.items():
            profile_version = versions.get(user_id, version)
            if not embeddings_compatible(version, profile_version):
                continue
            scores.append(
                self.score_user(probe, embeddings, user_id=user_id)
            )

        if not scores:
            return SpeakerVerificationResult(
                decision=VerificationDecision.VERSION_MISMATCH,
                outcome=VerificationOutcome.FAILED,
                recognition_band=RecognitionBand.INACTIVE,
                confidence=0.0,
                threshold=threshold,
                matched_user=None,
                reason="embedding_version_mismatch",
                embedding_version=version,
                production_trusted=production_trusted,
            )

        scores.sort(key=lambda item: item.score, reverse=True)
        best = scores[0]
        second = scores[1] if len(scores) > 1 else None

        # Closed-set enrollment verify against a single expected user.
        if expected_user_id is not None:
            return self._verify_expected(
                best=best,
                scores=tuple(scores),
                expected_user_id=expected_user_id,
                version=version,
                production_trusted=production_trusted,
                threshold=threshold,
            )

        # Open-set identification — prefer UNKNOWN / AMBIGUOUS.
        if (
            second is not None
            and (best.score - second.score) <= self._config.ambiguity_delta
            and best.score >= self._config.medium_threshold
        ):
            return SpeakerVerificationResult(
                decision=VerificationDecision.AMBIGUOUS,
                outcome=VerificationOutcome.AMBIGUOUS,
                recognition_band=RecognitionBand.AMBIGUOUS,
                confidence=best.score,
                threshold=threshold,
                matched_user=None,
                reason="ambiguous_match",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=tuple(scores),
                second_best_user=second.user_id,
                second_best_score=second.score,
            )

        if best.score >= self._config.high_threshold:
            return SpeakerVerificationResult(
                decision=VerificationDecision.VERIFIED,
                outcome=VerificationOutcome.PASSED,
                recognition_band=RecognitionBand.HIGH,
                confidence=best.score,
                threshold=threshold,
                matched_user=best.user_id,
                reason="matched_voiceprint",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=tuple(scores),
                second_best_user=second.user_id if second else None,
                second_best_score=second.score if second else None,
            )

        if best.score >= self._config.medium_threshold:
            # Medium confidence: never auto-bind — UNKNOWN + confirm.
            return SpeakerVerificationResult(
                decision=VerificationDecision.UNKNOWN,
                outcome=VerificationOutcome.NEEDS_CONFIRMATION,
                recognition_band=RecognitionBand.MEDIUM,
                confidence=best.score,
                threshold=threshold,
                matched_user=best.user_id,
                reason="medium_confidence",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=tuple(scores),
                second_best_user=second.user_id if second else None,
                second_best_score=second.score if second else None,
            )

        return SpeakerVerificationResult(
            decision=VerificationDecision.REJECTED
            if best.score < self._config.medium_threshold / 2
            else VerificationDecision.UNKNOWN,
            outcome=VerificationOutcome.UNKNOWN,
            recognition_band=RecognitionBand.LOW,
            confidence=best.score,
            threshold=threshold,
            matched_user=best.user_id,
            reason="insufficient_confidence",
            embedding_version=version,
            production_trusted=production_trusted,
            scores=tuple(scores),
            second_best_user=second.user_id if second else None,
            second_best_score=second.score if second else None,
        )

    def _verify_expected(
        self,
        *,
        best: SpeakerScore,
        scores: tuple[SpeakerScore, ...],
        expected_user_id: str,
        version: str,
        production_trusted: bool,
        threshold: float,
    ) -> SpeakerVerificationResult:
        expected_score = next(
            (s for s in scores if s.user_id == expected_user_id), None
        )
        confidence = expected_score.score if expected_score else 0.0
        # If another user scores higher / near-equal, reject as ambiguous.
        if (
            best.user_id != expected_user_id
            and best.score >= self._config.medium_threshold
        ):
            return SpeakerVerificationResult(
                decision=VerificationDecision.AMBIGUOUS,
                outcome=VerificationOutcome.AMBIGUOUS,
                recognition_band=RecognitionBand.AMBIGUOUS,
                confidence=confidence,
                threshold=threshold,
                matched_user=None,
                reason="cross_user_ambiguous",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=scores,
                second_best_user=best.user_id,
                second_best_score=best.score,
            )

        if confidence >= threshold:
            return SpeakerVerificationResult(
                decision=VerificationDecision.VERIFIED,
                outcome=VerificationOutcome.PASSED,
                recognition_band=RecognitionBand.HIGH,
                confidence=confidence,
                threshold=threshold,
                matched_user=expected_user_id,
                reason="verification_matched",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=scores,
            )

        if confidence >= self._config.medium_threshold:
            return SpeakerVerificationResult(
                decision=VerificationDecision.UNKNOWN,
                outcome=VerificationOutcome.NEEDS_CONFIRMATION,
                recognition_band=RecognitionBand.MEDIUM,
                confidence=confidence,
                threshold=threshold,
                matched_user=expected_user_id,
                reason="medium_confidence",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=scores,
            )

        ambiguous_floor = (
            self._config.medium_threshold - self._config.ambiguity_delta
        )
        if ambiguous_floor <= confidence < self._config.medium_threshold:
            return SpeakerVerificationResult(
                decision=VerificationDecision.AMBIGUOUS,
                outcome=VerificationOutcome.AMBIGUOUS,
                recognition_band=RecognitionBand.AMBIGUOUS,
                confidence=confidence,
                threshold=threshold,
                matched_user=None,
                reason="ambiguous_confidence",
                embedding_version=version,
                production_trusted=production_trusted,
                scores=scores,
            )

        return SpeakerVerificationResult(
            decision=VerificationDecision.UNKNOWN,
            outcome=VerificationOutcome.UNKNOWN,
            recognition_band=RecognitionBand.LOW,
            confidence=confidence,
            threshold=threshold,
            matched_user=None,
            reason="low_confidence",
            embedding_version=version,
            production_trusted=production_trusted,
            scores=scores,
        )


def verify_probe_against_profiles(
    *,
    probe_embedding: Iterable[float],
    enrolled: dict[str, list[list[float]]],
    config: VerificationConfig | None = None,
    profile_versions: dict[str, str] | None = None,
    expected_user_id: str | None = None,
) -> SpeakerVerificationResult:
    """Module-level convenience wrapper."""
    return SpeakerVerificationEngine(config).verify(
        probe_embedding=probe_embedding,
        enrolled=enrolled,
        profile_versions=profile_versions,
        expected_user_id=expected_user_id,
    )

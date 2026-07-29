# =====================================
# Titan Enrollment Verification Pipeline
# =====================================

"""Verification against future production embeddings (Phase 20.10A / 20.11).

Supports confidence thresholds and retry workflow. Never exposes embeddings
or raw recordings. Phase 20.11 delegates scoring to SpeakerVerificationEngine
(cosine / provider similarity, UNKNOWN / AMBIGUOUS, multi-sample aggregation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from voice.embedding_provider import get_embedding_provider
from voice.enrollment_models import (
    EnrollmentConfig,
    EnrollmentVerificationResult,
    VerificationOutcome,
)
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    VerificationConfig,
)


@dataclass(frozen=True)
class VerificationThresholds:
    """Configurable verification confidence bands."""

    high: float = 0.72
    medium: float = 0.55
    pass_threshold: float = 0.72
    ambiguity_delta: float = 0.05
    max_retries: int = 3

    @classmethod
    def from_config(cls, config: EnrollmentConfig) -> VerificationThresholds:
        return cls(
            high=config.high_confidence,
            medium=config.medium_confidence,
            pass_threshold=config.min_enrollment_confidence,
            ambiguity_delta=config.ambiguity_delta,
            max_retries=config.max_verification_retries,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "high": self.high,
            "medium": self.medium,
            "pass_threshold": self.pass_threshold,
            "ambiguity_delta": self.ambiguity_delta,
            "max_retries": self.max_retries,
        }


@dataclass(frozen=True)
class VerificationPipelineResult:
    """Full verification pipeline outcome (safe for API / diagnostics)."""

    verification: EnrollmentVerificationResult
    retry_allowed: bool
    retries_used: int
    retries_remaining: int
    embedding_version: str
    production_ready: bool
    probe_quality: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification": self.verification.to_dict(),
            "retry_allowed": self.retry_allowed,
            "retries_used": self.retries_used,
            "retries_remaining": self.retries_remaining,
            "embedding_version": self.embedding_version,
            "production_ready": self.production_ready,
            "probe_quality": (
                round(self.probe_quality, 4) if self.probe_quality is not None else None
            ),
        }


class EnrollmentVerificationPipeline:
    """Score a probe embedding against a pending enrollment profile."""

    def __init__(self, thresholds: VerificationThresholds | None = None) -> None:
        self._thresholds = thresholds or VerificationThresholds()

    @property
    def thresholds(self) -> VerificationThresholds:
        return self._thresholds

    def score_probe(
        self,
        *,
        probe_embedding: Iterable[float],
        profile_embeddings: list[list[float]],
        expected_user_id: str,
        profile_embedding_version: str,
        retries_used: int = 0,
        probe_quality: float | None = None,
    ) -> VerificationPipelineResult:
        """Compare probe to enrolled embeddings with confidence thresholds."""
        provider = get_embedding_provider()
        version = provider.embedding_version
        production_ready = provider.is_available and (
            provider.is_production_trusted or provider.is_dev_fallback
        )

        probe = [float(v) for v in probe_embedding]
        if not probe or not profile_embeddings:
            result = EnrollmentVerificationResult(
                matched_identity=None,
                confidence=0.0,
                threshold=self._thresholds.pass_threshold,
                outcome=VerificationOutcome.FAILED,
                reason="missing_embeddings",
            )
            return self._wrap(result, retries_used, version, production_ready, probe_quality)

        engine = SpeakerVerificationEngine(
            VerificationConfig(
                high_threshold=self._thresholds.pass_threshold,
                medium_threshold=self._thresholds.medium,
                ambiguity_delta=self._thresholds.ambiguity_delta,
            ),
            provider=provider,
        )
        verification = engine.verify(
            probe_embedding=probe,
            enrolled={expected_user_id: profile_embeddings},
            profile_versions={expected_user_id: profile_embedding_version},
            expected_user_id=expected_user_id,
        )

        result = EnrollmentVerificationResult(
            matched_identity=verification.matched_user,
            confidence=verification.confidence,
            threshold=verification.threshold,
            outcome=verification.outcome,
            reason=verification.reason,
            requires_confirmation=(
                verification.outcome == VerificationOutcome.NEEDS_CONFIRMATION
            ),
        )
        retryable = verification.outcome in {
            VerificationOutcome.NEEDS_CONFIRMATION,
            VerificationOutcome.AMBIGUOUS,
            VerificationOutcome.UNKNOWN,
        }
        return self._wrap(
            result,
            retries_used,
            version,
            production_ready,
            probe_quality,
            retryable=retryable,
        )

    def retry_allowed(self, retries_used: int) -> bool:
        return retries_used < self._thresholds.max_retries

    def _wrap(
        self,
        result: EnrollmentVerificationResult,
        retries_used: int,
        version: str,
        production_ready: bool,
        probe_quality: float | None,
        *,
        retryable: bool = False,
    ) -> VerificationPipelineResult:
        remaining = max(0, self._thresholds.max_retries - retries_used - (1 if retryable else 0))
        allowed = retryable and (retries_used + 1) < self._thresholds.max_retries
        if result.outcome == VerificationOutcome.PASSED:
            allowed = False
            remaining = max(0, self._thresholds.max_retries - retries_used)
        return VerificationPipelineResult(
            verification=result,
            retry_allowed=allowed,
            retries_used=retries_used + (0 if result.outcome == VerificationOutcome.PASSED else 1),
            retries_remaining=remaining if allowed else 0,
            embedding_version=version,
            production_ready=production_ready,
            probe_quality=probe_quality,
        )

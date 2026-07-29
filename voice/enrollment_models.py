# =====================================
# Titan Voice Enrollment Models
# =====================================

"""Structured models for Phase 20.2 voice enrollment and identity profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


METADATA_VERSION = 1
EMBEDDING_VERSION = "histogram_v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


class EnrollmentStatus(str, Enum):
    """Explicit enrollment lifecycle states (Phase 20.2–20.9 legacy API).

    Production workflow states live in ``voice.enrollment_workflow`` and are
    mirrored onto sessions via ``workflow_state`` without breaking this enum.
    """

    NOT_ENROLLED = "NOT_ENROLLED"
    AWAITING_CONSENT = "AWAITING_CONSENT"
    COLLECTING = "COLLECTING"
    VALIDATING = "VALIDATING"
    BUILDING_PROFILE = "BUILDING_PROFILE"
    VERIFYING = "VERIFYING"
    ENROLLED = "ENROLLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVOKED = "REVOKED"


class SampleRejectReason(str, Enum):
    """Safe rejection reasons for enrollment samples."""

    EMPTY = "empty_audio"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    CORRUPTED = "corrupted_audio"
    UNSUPPORTED = "unsupported_audio"
    EXCESSIVE_SILENCE = "excessive_silence"
    SEVERE_CLIPPING = "severe_clipping"
    DUPLICATE = "duplicate_sample"
    MULTI_SPEAKER = "multiple_speakers"
    LOW_QUALITY = "low_quality"
    LOW_SIGNAL = "low_signal_level"
    HIGH_NOISE = "background_noise"
    POOR_MICROPHONE = "poor_microphone_quality"
    LIMIT_REACHED = "sample_limit_reached"
    INVALID_STATE = "invalid_enrollment_state"


class VerificationOutcome(str, Enum):
    """Result of an enrollment verification pass."""

    PASSED = "passed"
    FAILED = "failed"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class RecognitionBand(str, Enum):
    """Runtime recognition confidence band."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    AMBIGUOUS = "ambiguous"
    INACTIVE = "inactive"


@dataclass
class EnrollmentConfig:
    """Configurable enrollment thresholds (safe defaults)."""

    min_sample_count: int = 3
    max_sample_count: int = 8
    min_sample_duration_seconds: float = 1.0
    max_sample_duration_seconds: float = 30.0
    min_quality_score: float = 0.45
    min_enrollment_confidence: float = 0.72
    high_confidence: float = 0.72
    medium_confidence: float = 0.55
    ambiguity_delta: float = 0.05
    max_verification_retries: int = 3
    assumed_sample_rate: int = 16000
    assumed_sample_width_bytes: int = 2
    assumed_channels: int = 1
    require_consent: bool = False
    recovery_ttl_seconds: float = 3600.0
    same_user_duplicate_threshold: float = 0.97
    consent_version: str = "v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_sample_count": self.min_sample_count,
            "max_sample_count": self.max_sample_count,
            "min_sample_duration_seconds": self.min_sample_duration_seconds,
            "max_sample_duration_seconds": self.max_sample_duration_seconds,
            "min_quality_score": self.min_quality_score,
            "min_enrollment_confidence": self.min_enrollment_confidence,
            "high_confidence": self.high_confidence,
            "medium_confidence": self.medium_confidence,
            "ambiguity_delta": self.ambiguity_delta,
            "max_verification_retries": self.max_verification_retries,
            "require_consent": self.require_consent,
            "recovery_ttl_seconds": self.recovery_ttl_seconds,
            "same_user_duplicate_threshold": self.same_user_duplicate_threshold,
            "consent_version": self.consent_version,
        }


@dataclass
class SampleValidationResult:
    """Outcome of validating one enrollment sample."""

    accepted: bool
    quality_score: float
    duration_seconds: float
    reason: str | None = None
    reject_code: SampleRejectReason | None = None
    feature_fingerprint: str | None = None
    production_metrics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "quality_score": round(self.quality_score, 4),
            "duration_seconds": round(self.duration_seconds, 4),
            "reason": self.reason,
            "reject_code": self.reject_code.value if self.reject_code else None,
        }
        if self.production_metrics is not None:
            payload["production_metrics"] = self.production_metrics
        return payload


@dataclass
class EnrollmentSampleRecord:
    """In-memory record of an accepted sample (no raw audio retained)."""

    sample_id: str
    quality_score: float
    duration_seconds: float
    feature_fingerprint: str
    embedding: list[float]
    phrase_index: int
    created_at: datetime = field(default_factory=_utc_now)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "quality_score": round(self.quality_score, 4),
            "duration_seconds": round(self.duration_seconds, 4),
            "phrase_index": self.phrase_index,
            "created_at": _iso(self.created_at),
        }


@dataclass
class SpeakerIdentityProfile:
    """Durable speaker identity profile (embeddings are private storage only)."""

    profile_id: str
    user_id: str
    display_name: str
    enrollment_status: EnrollmentStatus
    sample_count: int = 0
    embedding_version: str = EMBEDDING_VERSION
    confidence: float = 0.0
    quality_score: float = 0.0
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    last_verified_at: datetime | None = None
    active: bool = False
    revoked_at: datetime | None = None
    metadata_version: int = METADATA_VERSION
    embeddings: list[list[float]] = field(default_factory=list)
    enrollment_fingerprints: list[str] = field(default_factory=list)
    replaces_profile_id: str | None = None
    failure_reason: str | None = None
    profile_version: int = 1
    # Phase 20.11 — production trust never inferred from histogram alone.
    production_trusted: bool = False
    trust_level: str = "development_fallback"
    integrity_hash: str | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        display_name: str | None = None,
        status: EnrollmentStatus = EnrollmentStatus.BUILDING_PROFILE,
        profile_version: int = 1,
    ) -> SpeakerIdentityProfile:
        return cls(
            profile_id=str(uuid4()),
            user_id=user_id,
            display_name=display_name or user_id,
            enrollment_status=status,
            profile_version=max(1, int(profile_version)),
            production_trusted=False,
            trust_level="development_fallback",
        )

    def to_storage_dict(self) -> dict[str, Any]:
        """Full persistence payload including private embeddings."""
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "enrollment_status": self.enrollment_status.value,
            "sample_count": self.sample_count,
            "embedding_version": self.embedding_version,
            "confidence": round(self.confidence, 4),
            "quality_score": round(self.quality_score, 4),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "last_verified_at": _iso(self.last_verified_at),
            "active": self.active,
            "revoked_at": _iso(self.revoked_at),
            "metadata_version": self.metadata_version,
            "embeddings": self.embeddings,
            "enrollment_fingerprints": list(self.enrollment_fingerprints),
            "replaces_profile_id": self.replaces_profile_id,
            "failure_reason": self.failure_reason,
            "profile_version": self.profile_version,
            "production_trusted": self.production_trusted,
            "trust_level": self.trust_level,
            "integrity_hash": self.integrity_hash,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Safe metadata — never includes embeddings or fingerprints."""
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "enrollment_status": self.enrollment_status.value,
            "sample_count": self.sample_count,
            "embedding_version": self.embedding_version,
            "confidence": round(self.confidence, 4),
            "quality_score": round(self.quality_score, 4),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "last_verified_at": _iso(self.last_verified_at),
            "active": self.active,
            "revoked_at": _iso(self.revoked_at),
            "metadata_version": self.metadata_version,
            "replaces_profile_id": self.replaces_profile_id,
            "failure_reason": self.failure_reason,
            "profile_version": self.profile_version,
            "production_trusted": self.production_trusted,
            "trust_level": self.trust_level,
            # integrity present/absent only — never the hash contents needed to forge
            "has_integrity_seal": bool(self.integrity_hash),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeakerIdentityProfile:
        status_raw = data.get("enrollment_status", EnrollmentStatus.NOT_ENROLLED.value)
        try:
            status = EnrollmentStatus(str(status_raw))
        except ValueError:
            status = EnrollmentStatus.NOT_ENROLLED
        embeddings = [
            [float(v) for v in row]
            for row in data.get("embeddings", [])
            if isinstance(row, list)
        ]
        return cls(
            profile_id=str(data.get("profile_id") or uuid4()),
            user_id=str(data.get("user_id") or data.get("user") or ""),
            display_name=str(data.get("display_name") or data.get("user_id") or ""),
            enrollment_status=status,
            sample_count=int(data.get("sample_count", len(embeddings))),
            embedding_version=str(data.get("embedding_version", EMBEDDING_VERSION)),
            confidence=float(data.get("confidence", 0.0)),
            quality_score=float(data.get("quality_score", 0.0)),
            created_at=_parse_dt(data.get("created_at")) or _utc_now(),
            updated_at=_parse_dt(data.get("updated_at")) or _utc_now(),
            last_verified_at=_parse_dt(data.get("last_verified_at")),
            active=bool(data.get("active", False)),
            revoked_at=_parse_dt(data.get("revoked_at")),
            metadata_version=int(data.get("metadata_version", METADATA_VERSION)),
            embeddings=embeddings,
            enrollment_fingerprints=[
                str(item) for item in data.get("enrollment_fingerprints", [])
            ],
            replaces_profile_id=(
                str(data["replaces_profile_id"])
                if data.get("replaces_profile_id")
                else None
            ),
            failure_reason=(
                str(data["failure_reason"]) if data.get("failure_reason") else None
            ),
            profile_version=max(1, int(data.get("profile_version", 1))),
            production_trusted=bool(data.get("production_trusted", False)),
            trust_level=str(data.get("trust_level") or "development_fallback"),
            integrity_hash=(
                str(data["integrity_hash"]) if data.get("integrity_hash") else None
            ),
        )


@dataclass
class EnrollmentSession:
    """Guided enrollment session for one authorized user."""

    session_id: str
    user_id: str
    status: EnrollmentStatus
    locale: str = "fr-FR"
    script_id: str = "fr_default"
    samples: list[EnrollmentSampleRecord] = field(default_factory=list)
    required_samples: int = 3
    max_samples: int = 8
    quality_status: str = "pending"
    verification_status: str = "pending"
    verification_retries: int = 0
    pending_profile_id: str | None = None
    replacing_profile_id: str | None = None
    failure_reason: str | None = None
    session_label: str | None = None
    embedding_version: str = EMBEDDING_VERSION
    consent_given: bool = False
    consent_version: str | None = None
    consent_locale: str | None = None
    consent_at: datetime | None = None
    recovery_token: str | None = None
    aggregate_quality_score: float = 0.0
    processing_latency_ms: float = 0.0
    workflow_state: str = "WAITING_CONSENT"
    attempt_number: int = 1
    workflow_transitions: list[dict[str, Any]] = field(default_factory=list)
    last_quality_metrics: dict[str, Any] | None = None
    last_verification_confidence: float | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "locale": self.locale,
            "script_id": self.script_id,
            "samples": [
                {
                    "sample_id": sample.sample_id,
                    "quality_score": sample.quality_score,
                    "duration_seconds": sample.duration_seconds,
                    "feature_fingerprint": sample.feature_fingerprint,
                    "embedding": sample.embedding,
                    "phrase_index": sample.phrase_index,
                    "created_at": _iso(sample.created_at),
                }
                for sample in self.samples
            ],
            "required_samples": self.required_samples,
            "max_samples": self.max_samples,
            "quality_status": self.quality_status,
            "verification_status": self.verification_status,
            "verification_retries": self.verification_retries,
            "pending_profile_id": self.pending_profile_id,
            "replacing_profile_id": self.replacing_profile_id,
            "failure_reason": self.failure_reason,
            "session_label": self.session_label,
            "embedding_version": self.embedding_version,
            "consent_given": self.consent_given,
            "consent_version": self.consent_version,
            "consent_locale": self.consent_locale,
            "consent_at": _iso(self.consent_at),
            "recovery_token": self.recovery_token,
            "aggregate_quality_score": self.aggregate_quality_score,
            "processing_latency_ms": self.processing_latency_ms,
            "workflow_state": self.workflow_state,
            "attempt_number": self.attempt_number,
            "workflow_transitions": list(self.workflow_transitions),
            "last_quality_metrics": self.last_quality_metrics,
            "last_verification_confidence": self.last_verification_confidence,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "workflow_state": self.workflow_state,
            "attempt_number": self.attempt_number,
            "locale": self.locale,
            "script_id": self.script_id,
            "samples_collected": len(self.samples),
            "samples_required": self.required_samples,
            "samples_max": self.max_samples,
            "quality_status": self.quality_status,
            "verification_status": self.verification_status,
            "verification_retries": self.verification_retries,
            "pending_profile_id": self.pending_profile_id,
            "replacing_profile_id": self.replacing_profile_id,
            "failure_reason": self.failure_reason,
            "session_label": self.session_label,
            "embedding_version": self.embedding_version,
            "consent_given": self.consent_given,
            "consent_version": self.consent_version,
            "consent_locale": self.consent_locale,
            "consent_at": _iso(self.consent_at),
            "recovery_token": self.recovery_token,
            "aggregate_quality_score": round(self.aggregate_quality_score, 4),
            "processing_latency_ms": round(self.processing_latency_ms, 2),
            "last_quality_metrics": self.last_quality_metrics,
            "last_verification_confidence": (
                round(self.last_verification_confidence, 4)
                if self.last_verification_confidence is not None
                else None
            ),
            "workflow_transitions": list(self.workflow_transitions[-20:]),
            "samples": [s.to_safe_dict() for s in self.samples],
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnrollmentSession:
        status_raw = data.get("status", EnrollmentStatus.NOT_ENROLLED.value)
        try:
            status = EnrollmentStatus(str(status_raw))
        except ValueError:
            status = EnrollmentStatus.FAILED
        samples: list[EnrollmentSampleRecord] = []
        for item in data.get("samples", []):
            if not isinstance(item, dict):
                continue
            embedding = [float(v) for v in item.get("embedding", [])]
            samples.append(
                EnrollmentSampleRecord(
                    sample_id=str(item.get("sample_id", uuid4())),
                    quality_score=float(item.get("quality_score", 0.0)),
                    duration_seconds=float(item.get("duration_seconds", 0.0)),
                    feature_fingerprint=str(item.get("feature_fingerprint", "")),
                    embedding=embedding,
                    phrase_index=int(item.get("phrase_index", 0)),
                    created_at=_parse_dt(item.get("created_at")) or _utc_now(),
                )
            )
        return cls(
            session_id=str(data.get("session_id") or uuid4()),
            user_id=str(data.get("user_id", "")),
            status=status,
            locale=str(data.get("locale", "fr-FR")),
            script_id=str(data.get("script_id", "fr_default")),
            samples=samples,
            required_samples=int(data.get("required_samples", 3)),
            max_samples=int(data.get("max_samples", 8)),
            quality_status=str(data.get("quality_status", "pending")),
            verification_status=str(data.get("verification_status", "pending")),
            verification_retries=int(data.get("verification_retries", 0)),
            pending_profile_id=(
                str(data["pending_profile_id"])
                if data.get("pending_profile_id")
                else None
            ),
            replacing_profile_id=(
                str(data["replacing_profile_id"])
                if data.get("replacing_profile_id")
                else None
            ),
            failure_reason=(
                str(data["failure_reason"]) if data.get("failure_reason") else None
            ),
            session_label=(
                str(data["session_label"]) if data.get("session_label") else None
            ),
            embedding_version=str(data.get("embedding_version", EMBEDDING_VERSION)),
            consent_given=bool(data.get("consent_given", False)),
            consent_version=(
                str(data["consent_version"]) if data.get("consent_version") else None
            ),
            consent_locale=(
                str(data["consent_locale"]) if data.get("consent_locale") else None
            ),
            consent_at=_parse_dt(data.get("consent_at")),
            recovery_token=(
                str(data["recovery_token"]) if data.get("recovery_token") else None
            ),
            aggregate_quality_score=float(data.get("aggregate_quality_score", 0.0)),
            processing_latency_ms=float(data.get("processing_latency_ms", 0.0)),
            workflow_state=str(data.get("workflow_state") or "WAITING_CONSENT"),
            attempt_number=max(1, int(data.get("attempt_number", 1))),
            workflow_transitions=[
                dict(item)
                for item in data.get("workflow_transitions", [])
                if isinstance(item, dict)
            ],
            last_quality_metrics=(
                dict(data["last_quality_metrics"])
                if isinstance(data.get("last_quality_metrics"), dict)
                else None
            ),
            last_verification_confidence=(
                float(data["last_verification_confidence"])
                if data.get("last_verification_confidence") is not None
                else None
            ),
            created_at=_parse_dt(data.get("created_at")) or _utc_now(),
            updated_at=_parse_dt(data.get("updated_at")) or _utc_now(),
        )


@dataclass(frozen=True)
class EnrollmentVerificationResult:
    """Structured verification outcome (safe for API / diagnostics)."""

    matched_identity: str | None
    confidence: float
    threshold: float
    outcome: VerificationOutcome
    reason: str
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_identity": self.matched_identity,
            "confidence": round(self.confidence, 4),
            "threshold": round(self.threshold, 4),
            "verification_result": self.outcome.value,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
        }

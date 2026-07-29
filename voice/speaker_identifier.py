# =====================================
# Titan Speaker Identifier
# =====================================

"""Speaker identification for Nolan vs Ibrahim (Phase 20.1 + 20.2 + 20.11).

Enforces Constitution Article 1.5: unknown or low-confidence speakers must
confirm identity before personal memory is bound via SessionManager.

Phase 20.2 adds recognition bands (high / medium / low), ambiguous-match
protection, and active/revoked profile filtering via SpeakerProfileStore.

Phase 20.11 routes matching through SpeakerVerificationEngine and enforces
the identity security boundary (voice ID ≠ high-risk authorization).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from context.session_manager import AUTHORIZED_USERS, SessionManager
from voice.enrollment_models import EnrollmentStatus, RecognitionBand
from voice.exceptions import VoiceConfigurationError
from voice.identity_security import (
    IdentityAssertionKind,
    IdentitySecurityBoundary,
    voice_identity_may_access_personal_memory,
)
from voice.speaker_verification import (
    SpeakerVerificationEngine,
    VerificationConfig,
    VerificationDecision,
)

logger = logging.getLogger(__name__)

FEATURE_DIM = 32
DEFAULT_MIN_CONFIDENCE = 0.72
DEFAULT_MEDIUM_CONFIDENCE = 0.55
DEFAULT_AMBIGUITY_DELTA = 0.05
_CONFIRM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bje\s+suis\s+nolan\b", "Nolan"),
    (r"\bc['’]?est\s+nolan\b", "Nolan"),
    (r"\bnolan\b", "Nolan"),
    (r"\bje\s+suis\s+ibrahim\b", "Ibrahim"),
    (r"\bc['’]?est\s+ibrahim\b", "Ibrahim"),
    (r"\bibrahim\b", "Ibrahim"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


class SpeakerIdentity(str, Enum):
    """Canonical voice identity labels."""

    NOLAN = "Nolan"
    IBRAHIM = "Ibrahim"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SpeakerIdentificationResult:
    """Outcome of one identification attempt."""

    identity: SpeakerIdentity
    confidence: float
    requires_confirmation: bool
    reason: str
    matched_user: str | None = None
    recognition_band: RecognitionBand | None = None
    threshold: float | None = None
    production_trusted: bool = False
    embedding_version: str | None = None
    decision: str | None = None
    assertion_kind: IdentityAssertionKind = IdentityAssertionKind.UNKNOWN

    @property
    def is_known(self) -> bool:
        return self.identity in {SpeakerIdentity.NOLAN, SpeakerIdentity.IBRAHIM}

    @property
    def is_biometrically_verified(self) -> bool:
        return self.assertion_kind == IdentityAssertionKind.VERIFIED_IDENTITY

    @property
    def is_claimed_only(self) -> bool:
        return self.assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.value,
            "confidence": round(self.confidence, 4),
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
            "matched_user": self.matched_user,
            "is_known": self.is_known,
            "recognition_band": (
                self.recognition_band.value if self.recognition_band else None
            ),
            "threshold": (
                round(self.threshold, 4) if self.threshold is not None else None
            ),
            "production_trusted": self.production_trusted,
            "embedding_version": self.embedding_version,
            "decision": self.decision,
            "assertion_kind": self.assertion_kind.value,
            "is_biometrically_verified": self.is_biometrically_verified,
            "is_claimed_only": self.is_claimed_only,
        }


@dataclass
class SpeakerProfile:
    """Enrolled voiceprint for one authorized user."""

    user: str
    embeddings: list[list[float]] = field(default_factory=list)
    sample_count: int = 0
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user": self.user,
            "embeddings": self.embeddings,
            "sample_count": self.sample_count,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeakerProfile:
        created = (
            datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else _utc_now()
        )
        updated = (
            datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else created
        )
        embeddings = [
            [float(v) for v in row]
            for row in data.get("embeddings", [])
            if isinstance(row, list)
        ]
        return cls(
            user=str(data.get("user", "")),
            embeddings=embeddings,
            sample_count=int(data.get("sample_count", len(embeddings))),
            created_at=created,
            updated_at=updated,
        )


def extract_voice_features(audio_bytes: bytes) -> list[float]:
    """Build a lightweight fixed-size voiceprint from raw audio bytes.

    Delegates to the pluggable embedding provider (default: histogram_v1).
    No ML dependency — language-independent acoustic features.
    """
    from voice.embedding_provider import get_embedding_provider

    return get_embedding_provider().extract(audio_bytes)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Legacy helper — prefer provider.similarity / SpeakerVerificationEngine."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def parse_spoken_identity(text: str) -> str | None:
    """Extract Nolan/Ibrahim from a confirmation utterance."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return None
    for pattern, user in _CONFIRM_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return user
    return None


UNKNOWN_SPEAKER_PROMPT = (
    "Je ne te reconnais pas clairement. Es-tu Nolan ou Ibrahim ? "
    "Dis par exemple « je suis Nolan » ou « je suis Ibrahim »."
)


class SpeakerIdentifier:
    """Enrollment + identification with confirm-on-unknown protocol."""

    def __init__(
        self,
        *,
        file_path: Path | str | None = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        medium_confidence: float = DEFAULT_MEDIUM_CONFIDENCE,
        ambiguity_delta: float = DEFAULT_AMBIGUITY_DELTA,
        enabled: bool = True,
        profile_store: Any | None = None,
    ) -> None:
        self.file_path = Path(file_path) if file_path else None
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.medium_confidence = max(
            0.0, min(self.min_confidence, float(medium_confidence))
        )
        self.ambiguity_delta = max(0.0, float(ambiguity_delta))
        self.enabled = bool(enabled)
        self._profile_store = profile_store
        self._profiles: dict[str, SpeakerProfile] = {}
        self._profile_versions: dict[str, str] = {}
        self._pending_confirmation = False
        self._loaded = False
        from voice.biometric_trust import production_verification_defaults
        from voice.speaker_verification import default_verification_config

        # Prefer settings-aware defaults; fall back to constructor thresholds.
        try:
            base_cfg = default_verification_config()
            cfg = VerificationConfig(
                high_threshold=self.min_confidence,
                medium_threshold=self.medium_confidence,
                ambiguity_delta=self.ambiguity_delta,
                require_production_trust=base_cfg.require_production_trust,
                allow_dev_fallback_identity=base_cfg.allow_dev_fallback_identity,
                aggregation=base_cfg.aggregation,
            )
        except Exception:
            defaults = production_verification_defaults()
            cfg = VerificationConfig(
                high_threshold=self.min_confidence,
                medium_threshold=self.medium_confidence,
                ambiguity_delta=self.ambiguity_delta,
                require_production_trust=defaults["require_production_trust"],
                allow_dev_fallback_identity=defaults["allow_dev_fallback_identity"],
            )
        self._verification = SpeakerVerificationEngine(cfg)
        self._security = IdentitySecurityBoundary()

    def attach_profile_store(self, store: Any) -> None:
        """Wire Phase 20.2 SpeakerProfileStore for active-profile recognition."""
        self._profile_store = store
        self._loaded = False

    def load(self) -> None:
        """Load enrolled profiles from store or legacy disk schema."""
        if self._loaded:
            return
        self._loaded = True
        if self._profile_store is not None:
            self._load_from_store()
            return
        if self.file_path is None or not self.file_path.exists():
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Corrupt speaker profiles file %s: %s", self.file_path, exc)
            raise VoiceConfigurationError(
                f"Failed to load speaker profiles: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            return
        schema = int(raw.get("schema_version", 1))
        if schema >= 2:
            # Prefer store semantics when encountering v2 files without a store.
            from voice.speaker_profile_store import SpeakerProfileStore

            store = SpeakerProfileStore(file_path=self.file_path)
            store.load()
            self._profile_store = store
            self._load_from_store()
            return
        profiles = raw.get("profiles", {})
        for user, payload in profiles.items():
            if not isinstance(payload, dict):
                continue
            normalized = SessionManager.normalize_user(str(user))
            if normalized is None:
                continue
            profile = SpeakerProfile.from_dict({**payload, "user": normalized})
            self._profiles[normalized] = profile

    def _load_from_store(self) -> None:
        assert self._profile_store is not None
        active = self._profile_store.list_active_embeddings()
        self._profiles = {}
        self._profile_versions = {}
        for user, embeddings in active.items():
            normalized = SessionManager.normalize_user(str(user))
            if normalized is None:
                continue
            self._profiles[normalized] = SpeakerProfile(
                user=normalized,
                embeddings=[list(row) for row in embeddings],
                sample_count=len(embeddings),
            )
            profile = self._profile_store.get_active_profile(normalized)
            if profile is not None:
                self._profile_versions[normalized] = profile.embedding_version

    def reload(self) -> None:
        """Force reload after enrollment activation / revocation."""
        self._loaded = False
        self.load()

    def save(self) -> None:
        """Persist enrolled profiles when a path is configured."""
        if self._profile_store is not None:
            # Phase 20.2 store owns persistence; identifier only mirrors active set.
            return
        if self.file_path is None:
            return
        self.load()
        payload = {
            "schema_version": 1,
            "profiles": {
                user: profile.to_dict() for user, profile in self._profiles.items()
            },
        }
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)

    @property
    def pending_confirmation(self) -> bool:
        return self._pending_confirmation

    def list_enrolled_users(self) -> list[str]:
        self.load()
        return sorted(self._profiles)

    def enroll(self, user: str, audio_samples: list[bytes]) -> SpeakerProfile:
        """Enroll or extend a voiceprint for an authorized user.

        Legacy Phase 20.1 path — activates immediately. Prefer
        ``VoiceEnrollmentService`` for guided enrollment with verification.
        """
        self.load()
        normalized = SessionManager.normalize_user(user)
        if normalized is None:
            raise VoiceConfigurationError(
                f"Cannot enroll unauthorized user {user!r}. "
                f"Authorized: {sorted(AUTHORIZED_USERS)}"
            )
        samples = [s for s in audio_samples if s]
        if not samples:
            raise VoiceConfigurationError("At least one non-empty audio sample is required")

        if self._profile_store is not None:
            from voice.enrollment_models import SpeakerIdentityProfile

            embeddings = [extract_voice_features(sample) for sample in samples]
            existing = self._profile_store.get_active_profile(normalized)
            if existing is not None:
                existing.embeddings.extend(embeddings)
                if len(existing.embeddings) > 16:
                    existing.embeddings = existing.embeddings[-16:]
                existing.sample_count = len(existing.embeddings)
                existing.active = True
                existing.enrollment_status = EnrollmentStatus.ENROLLED
                existing.updated_at = _utc_now()
                self._profile_store.update_profile(existing)
                identity = existing
            else:
                identity = SpeakerIdentityProfile.create(
                    user_id=normalized,
                    display_name=normalized,
                    status=EnrollmentStatus.ENROLLED,
                )
                identity.embeddings = embeddings[:16]
                identity.sample_count = len(identity.embeddings)
                identity.active = True
                identity.confidence = 1.0
                identity.quality_score = 1.0
                identity.last_verified_at = _utc_now()
                self._profile_store.create_profile(identity)
                self._profile_store.activate_profile(identity.profile_id)
            self.reload()
            mirrored = self._profiles[normalized]
            logger.info(
                "SPEAKER_ENROLLED user=%s samples=%d total=%d",
                normalized,
                len(samples),
                mirrored.sample_count,
            )
            return mirrored

        profile = self._profiles.get(normalized) or SpeakerProfile(user=normalized)
        for sample in samples:
            profile.embeddings.append(extract_voice_features(sample))
        # Keep a bounded history for matching.
        if len(profile.embeddings) > 16:
            profile.embeddings = profile.embeddings[-16:]
        profile.sample_count = len(profile.embeddings)
        profile.updated_at = _utc_now()
        self._profiles[normalized] = profile
        self.save()
        logger.info(
            "SPEAKER_ENROLLED user=%s samples=%d total=%d",
            normalized,
            len(samples),
            profile.sample_count,
        )
        return profile

    def identify(self, audio_bytes: bytes) -> SpeakerIdentificationResult:
        """Identify speaker from audio; unknown when confidence is insufficient."""
        self.load()
        if self._profile_store is not None:
            # Refresh active set so revoked/inactive profiles never authenticate.
            self.reload()
        if not self.enabled:
            return SpeakerIdentificationResult(
                identity=SpeakerIdentity.UNKNOWN,
                confidence=0.0,
                requires_confirmation=False,
                reason="speaker_identification_disabled",
                recognition_band=RecognitionBand.INACTIVE,
            )
        if not audio_bytes:
            self._pending_confirmation = True
            return SpeakerIdentificationResult(
                identity=SpeakerIdentity.UNKNOWN,
                confidence=0.0,
                requires_confirmation=True,
                reason="empty_audio",
                recognition_band=RecognitionBand.LOW,
            )
        if not self._profiles:
            self._pending_confirmation = True
            return SpeakerIdentificationResult(
                identity=SpeakerIdentity.UNKNOWN,
                confidence=0.0,
                requires_confirmation=True,
                reason="no_enrolled_profiles",
                recognition_band=RecognitionBand.LOW,
            )

        probe = extract_voice_features(audio_bytes)
        enrolled = {
            user: list(profile.embeddings)
            for user, profile in self._profiles.items()
            if profile.embeddings
        }
        verification = self._verification.verify(
            probe_embedding=probe,
            enrolled=enrolled,
            profile_versions=self._profile_versions or None,
        )

        if verification.decision == VerificationDecision.AMBIGUOUS:
            self._pending_confirmation = True
            return SpeakerIdentificationResult(
                identity=SpeakerIdentity.UNKNOWN,
                confidence=verification.confidence,
                requires_confirmation=True,
                reason=verification.reason,
                matched_user=None,
                recognition_band=RecognitionBand.AMBIGUOUS,
                threshold=verification.threshold,
                production_trusted=verification.production_trusted,
                embedding_version=verification.embedding_version,
                decision=verification.decision.value,
            )

        if (
            verification.decision
            in {VerificationDecision.MATCHED, VerificationDecision.VERIFIED}
            and verification.matched_user
        ):
            best_user = verification.matched_user
            identity = (
                SpeakerIdentity.NOLAN if best_user == "Nolan" else SpeakerIdentity.IBRAHIM
            )
            self._pending_confirmation = False
            return SpeakerIdentificationResult(
                identity=identity,
                confidence=verification.confidence,
                requires_confirmation=False,
                reason=verification.reason,
                matched_user=best_user,
                recognition_band=RecognitionBand.HIGH,
                threshold=verification.threshold,
                production_trusted=verification.production_trusted,
                embedding_version=verification.embedding_version,
                decision=verification.decision.value,
                assertion_kind=IdentityAssertionKind.VERIFIED_IDENTITY,
            )

        # Prefer UNKNOWN over incorrect identification for all other bands.
        self._pending_confirmation = True
        band = verification.recognition_band or RecognitionBand.LOW
        return SpeakerIdentificationResult(
            identity=SpeakerIdentity.UNKNOWN,
            confidence=verification.confidence,
            requires_confirmation=True,
            reason=verification.reason,
            matched_user=verification.matched_user,
            recognition_band=band,
            threshold=verification.threshold,
            production_trusted=verification.production_trusted,
            embedding_version=verification.embedding_version,
            decision=verification.decision.value,
        )

    def confirm_from_text(self, text: str) -> SpeakerIdentificationResult:
        """Accept an explicit spoken claim of identity (CLAIMED, not VERIFIED).

        Saying « je suis Nolan » must never become biometrically VERIFIED.
        """
        user = parse_spoken_identity(text)
        if user is None:
            self._pending_confirmation = True
            return SpeakerIdentificationResult(
                identity=SpeakerIdentity.UNKNOWN,
                confidence=0.0,
                requires_confirmation=True,
                reason="confirmation_unrecognized",
                recognition_band=RecognitionBand.LOW,
                assertion_kind=IdentityAssertionKind.UNKNOWN,
            )
        identity = (
            SpeakerIdentity.NOLAN if user == "Nolan" else SpeakerIdentity.IBRAHIM
        )
        self._pending_confirmation = False
        logger.info("SPEAKER_CLAIMED user=%s via=text", user)
        return SpeakerIdentificationResult(
            identity=identity,
            confidence=1.0,
            requires_confirmation=False,
            reason="explicit_confirmation_claimed",
            matched_user=user,
            recognition_band=RecognitionBand.MEDIUM,
            threshold=1.0,
            production_trusted=False,
            assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY,
            decision="claimed",
        )

    def bind_session_user(
        self,
        session: SessionManager,
        result: SpeakerIdentificationResult,
        *,
        require_verified_for_personal_memory: bool = True,
    ) -> tuple[bool, str]:
        """Bind SessionManager.current_user when identity is known.

        Returns (bound, french_message). Unknown speakers are not bound.
        Speaker recognition alone must never authorize destructive actions.

        Claimed identity may still label the session for conversational UX,
        but personal-memory access requiring verification remains gated.
        """
        if not result.is_known or result.matched_user is None:
            return False, UNKNOWN_SPEAKER_PROMPT
        security = self._security.assert_not_authorization()
        if security.get("may_authorize_destructive"):
            return False, UNKNOWN_SPEAKER_PROMPT
        if require_verified_for_personal_memory and result.is_claimed_only:
            # Session label is allowed; callers must not treat this as verified.
            ok, message = session.set_user(result.matched_user)
            if ok:
                logger.info(
                    "SPEAKER_BOUND_CLAIMED user=%s confidence=%.4f reason=%s "
                    "personal_memory=blocked",
                    result.matched_user,
                    result.confidence,
                    result.reason,
                )
            return ok, message
        if (
            require_verified_for_personal_memory
            and not result.is_biometrically_verified
            and result.assertion_kind != IdentityAssertionKind.CLAIMED_IDENTITY
        ):
            # Medium/unknown bands: do not bind.
            if result.identity == SpeakerIdentity.UNKNOWN:
                return False, UNKNOWN_SPEAKER_PROMPT
        ok, message = session.set_user(result.matched_user)
        if ok:
            logger.info(
                "SPEAKER_BOUND user=%s confidence=%.4f reason=%s assertion=%s",
                result.matched_user,
                result.confidence,
                result.reason,
                result.assertion_kind.value,
            )
        return ok, message

    def may_access_personal_memory(
        self, result: SpeakerIdentificationResult
    ) -> bool:
        """True only for biometrically VERIFIED identity."""
        return voice_identity_may_access_personal_memory(
            assertion_kind=result.assertion_kind
        )

    def status(self) -> dict[str, Any]:
        self.load()
        from voice.embedding_provider import get_embedding_provider

        provider = get_embedding_provider()
        return {
            "enabled": self.enabled,
            "min_confidence": self.min_confidence,
            "medium_confidence": self.medium_confidence,
            "ambiguity_delta": self.ambiguity_delta,
            "enrolled_users": self.list_enrolled_users(),
            "pending_confirmation": self._pending_confirmation,
            "profiles_path": str(self.file_path) if self.file_path else None,
            "embedding_provider": provider.provider_id,
            "embedding_version": provider.embedding_version,
            "production_trusted": provider.is_production_trusted,
            "is_dev_fallback": provider.is_dev_fallback,
            "identity_security": self._security.assert_not_authorization(),
        }

# =====================================
# Titan Voice Enrollment Service
# =====================================

"""Guided voice enrollment lifecycle for Nolan and Ibrahim (Phase 20.2).

Processes raw audio transiently, stores only derived profile embeddings,
and activates profiles only after a successful verification pass.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from context.session_manager import AUTHORIZED_USERS, SessionManager
from voice.diagnostics import emit_voice_diagnostic
from voice.enrollment_audit import make_audit_event
from voice.enrollment_consent import get_consent_prompt, record_consent
from voice.enrollment_models import (
    EMBEDDING_VERSION,
    EnrollmentConfig,
    EnrollmentSampleRecord,
    EnrollmentSession,
    EnrollmentStatus,
    EnrollmentVerificationResult,
    SampleRejectReason,
    SpeakerIdentityProfile,
    VerificationOutcome,
)
from voice.enrollment_scripts import get_enrollment_script, list_enrollment_scripts
from voice.enrollment_verification import (
    EnrollmentVerificationPipeline,
    VerificationThresholds,
)
from voice.enrollment_workflow import (
    EnrollmentWorkflowController,
    ProductionEnrollmentState,
    legacy_to_production,
)
from voice.exceptions import VoiceConfigurationError, VoiceEnrollmentError
from voice.sample_validator import feature_fingerprint, validate_enrollment_sample
from voice.speaker_identifier import extract_voice_features
from voice.speaker_profile_store import SpeakerProfileStore

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class VoiceEnrollmentService:
    """Guided enrollment orchestration with privacy-safe persistence."""

    def __init__(
        self,
        *,
        store: SpeakerProfileStore | None = None,
        config: EnrollmentConfig | None = None,
        state_manager: Any | None = None,
        temp_dir: Path | str | None = None,
    ) -> None:
        self._store = store or SpeakerProfileStore()
        self._config = config or EnrollmentConfig()
        self._state_manager = state_manager
        self._temp_root = Path(temp_dir) if temp_dir else None
        self._workflow = EnrollmentWorkflowController()
        self._verification = EnrollmentVerificationPipeline(
            VerificationThresholds.from_config(self._config)
        )

    @property
    def store(self) -> SpeakerProfileStore:
        return self._store

    @property
    def config(self) -> EnrollmentConfig:
        return self._config

    def start_enrollment(
        self,
        *,
        target_user: str,
        authenticated_user: str,
        locale: str | None = None,
        replace_existing: bool = False,
        session_label: str | None = None,
        consent_accepted: bool = False,
    ) -> dict[str, Any]:
        """Start guided enrollment for an authorized user.

        Requires the authenticated user to match the enrollment target.
        Multiple historical sessions are retained; only one may be in-flight.
        When ``require_consent`` is enabled, samples are blocked until consent
        is granted (inline via ``consent_accepted`` or ``grant_consent``).
        """
        t0 = time.perf_counter()
        target = SessionManager.normalize_user(target_user)
        auth = SessionManager.normalize_user(authenticated_user)
        if target is None:
            raise VoiceEnrollmentError(
                f"Cannot enroll unauthorized user {target_user!r}. "
                f"Authorized: {sorted(AUTHORIZED_USERS)}",
                code="unauthorized_target",
            )
        if auth is None:
            raise VoiceEnrollmentError(
                "Enrollment requires an authenticated authorized user.",
                code="unauthorized",
            )
        if auth != target:
            raise VoiceEnrollmentError(
                "You may only enroll your own voice identity.",
                code="unauthorized_target_mismatch",
            )

        existing_active = self._store.get_active_profile(target)
        if existing_active is not None and not replace_existing:
            raise VoiceEnrollmentError(
                f"{target} already has an active voice profile. "
                "Pass replace_existing=true to re-enroll securely.",
                code="already_enrolled",
            )

        # Cancel any in-flight session for this user (history retained).
        prior = self._store.get_active_session_for_user(target)
        prior_attempts = 0
        if prior is not None:
            prior_attempts = max(prior.attempt_number, 0)
            self._set_workflow(
                prior,
                ProductionEnrollmentState.CANCELLED,
                reason="superseded_by_new_enrollment",
                force=True,
            )
            prior.status = EnrollmentStatus.CANCELLED
            prior.failure_reason = "superseded_by_new_enrollment"
            self._store.save_session(prior)
            self._cleanup_temp(prior.session_id)
            self._audit(
                "enrollment_superseded",
                user_id=target,
                session_id=prior.session_id,
                workflow_state=ProductionEnrollmentState.CANCELLED.value,
                attempt_number=prior.attempt_number,
            )

        from voice.embedding_provider import get_embedding_provider
        from voice.enrollment_quality import safe_profile_replacement_plan

        script = get_enrollment_script(locale)
        consent_prompt = get_consent_prompt(locale)
        consent_ok = bool(consent_accepted) or not self._config.require_consent
        consent_record = record_consent(
            accepted=consent_ok,
            locale=locale,
            version=self._config.consent_version,
            method="start_inline" if consent_accepted else "deferred",
        )
        initial_status = (
            EnrollmentStatus.COLLECTING
            if consent_ok
            else EnrollmentStatus.AWAITING_CONSENT
        )
        workflow_state = EnrollmentWorkflowController.initial_state(
            consent_given=consent_ok
        )
        attempt_number = prior_attempts + 1
        history = self._store.list_sessions_for_user(target)
        if history and attempt_number <= 1:
            attempt_number = len(history) + 1
        session = EnrollmentSession(
            session_id=str(uuid4()),
            user_id=target,
            status=initial_status,
            locale=script.locale,
            script_id=script.script_id,
            required_samples=self._config.min_sample_count,
            max_samples=self._config.max_sample_count,
            replacing_profile_id=(
                existing_active.profile_id if existing_active else None
            ),
            quality_status="awaiting_consent" if not consent_ok else "awaiting_samples",
            verification_status="pending",
            session_label=(session_label or "").strip() or None,
            embedding_version=get_embedding_provider().embedding_version,
            consent_given=consent_record.given,
            consent_version=consent_record.version if consent_record.given else None,
            consent_locale=consent_record.locale if consent_record.given else None,
            consent_at=(
                datetime.fromisoformat(consent_record.recorded_at)
                if consent_record.recorded_at
                else None
            ),
            recovery_token=uuid4().hex,
            workflow_state=workflow_state.value,
            attempt_number=attempt_number,
        )
        self._workflow.load_history([])
        boot = self._workflow.transition(
            ProductionEnrollmentState.WAITING_CONSENT,
            workflow_state,
            reason="enrollment_started",
            attempt_number=attempt_number,
            force=True,
        )
        session.workflow_transitions.append(boot.to_dict())
        session.processing_latency_ms = (time.perf_counter() - t0) * 1000.0
        self._ensure_temp_root()
        self._store.save_session(session)
        self._sync_workspace(session)
        self._audit(
            "enrollment_started",
            user_id=target,
            session_id=session.session_id,
            workflow_state=session.workflow_state,
            attempt_number=attempt_number,
            metadata={"replace_existing": bool(existing_active), "consent": consent_ok},
        )
        replace_plan = safe_profile_replacement_plan(
            existing_profile_id=existing_active.profile_id if existing_active else None,
            new_profile_id="pending",
            replace_existing=replace_existing,
        )
        logger.info(
            "VOICE_ENROLLMENT_STARTED user=%s session=%s replace=%s label=%s consent=%s attempt=%d workflow=%s",
            target,
            session.session_id,
            bool(existing_active),
            session.session_label,
            session.consent_given,
            attempt_number,
            session.workflow_state,
        )
        return {
            "ok": True,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "script": script.to_dict(),
            "consent": consent_prompt.to_dict(),
            "consent_record": consent_record.to_dict(),
            "next_phrase": (
                script.phrase_for_index(0) if consent_ok else None
            ),
            "config": self._config.to_dict(),
            "replacement_plan": replace_plan,
            "enrollment_history_count": len(
                self._store.list_sessions_for_user(target)
            ),
            "available_scripts": list_enrollment_scripts(),
            "audit_history": self._store.list_audit_history(user_id=target, limit=20),
        }

    def grant_consent(
        self,
        *,
        session_id: str,
        authenticated_user: str,
        accepted: bool = True,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Record enrollment consent and unlock sample collection."""
        session = self._require_session(session_id, authenticated_user)
        if session.status not in {
            EnrollmentStatus.AWAITING_CONSENT,
            EnrollmentStatus.COLLECTING,
        }:
            raise VoiceEnrollmentError(
                f"Cannot grant consent in state {session.status.value}",
                code="invalid_state",
            )
        if not accepted:
            self._set_workflow(
                session,
                ProductionEnrollmentState.CANCELLED,
                reason="consent_declined",
            )
            session.status = EnrollmentStatus.CANCELLED
            session.failure_reason = "consent_declined"
            session.consent_given = False
            self._store.save_session(session)
            self._cleanup_temp(session.session_id)
            self._sync_workspace(session, clear_when_idle=True)
            self._audit(
                "consent_declined",
                user_id=session.user_id,
                session_id=session.session_id,
                workflow_state=session.workflow_state,
                attempt_number=session.attempt_number,
            )
            logger.info(
                "VOICE_ENROLLMENT_CONSENT_DECLINED session=%s user=%s",
                session.session_id,
                session.user_id,
            )
            emit_voice_diagnostic(
                "VOICE_ENROLLMENT_CONSENT_DECLINED",
                session_id=session.session_id,
                user_id=session.user_id,
            )
            return {
                "ok": False,
                "accepted": False,
                "session": session.to_public_dict(),
                "workflow": self._workflow_snapshot(session).to_dict(),
                "error": "consent_declined",
            }

        record = record_consent(
            accepted=True,
            locale=locale or session.locale,
            version=self._config.consent_version,
            method="grant_consent",
        )
        session.consent_given = True
        session.consent_version = record.version
        session.consent_locale = record.locale
        session.consent_at = (
            datetime.fromisoformat(record.recorded_at)
            if record.recorded_at
            else _utc_now()
        )
        # Production path: WAITING_CONSENT → CONSENT_GRANTED → READY_TO_RECORD
        current_wf = self._current_workflow(session)
        if current_wf == ProductionEnrollmentState.WAITING_CONSENT:
            self._set_workflow(
                session,
                ProductionEnrollmentState.CONSENT_GRANTED,
                reason="consent_granted",
            )
            self._set_workflow(
                session,
                ProductionEnrollmentState.READY_TO_RECORD,
                reason="ready_after_consent",
            )
        elif current_wf != ProductionEnrollmentState.READY_TO_RECORD:
            self._set_workflow(
                session,
                ProductionEnrollmentState.READY_TO_RECORD,
                reason="consent_confirmed",
                force=True,
            )
        session.status = EnrollmentStatus.COLLECTING
        session.quality_status = "awaiting_samples"
        self._store.save_session(session)
        self._sync_workspace(session)
        self._audit(
            "consent_granted",
            user_id=session.user_id,
            session_id=session.session_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
            metadata={"consent_version": session.consent_version},
        )
        script = get_enrollment_script(session.script_id)
        logger.info(
            "VOICE_ENROLLMENT_CONSENT_GRANTED session=%s user=%s version=%s",
            session.session_id,
            session.user_id,
            session.consent_version,
        )
        emit_voice_diagnostic(
            "VOICE_ENROLLMENT_CONSENT_GRANTED",
            session_id=session.session_id,
            user_id=session.user_id,
            consent_version=session.consent_version,
        )
        return {
            "ok": True,
            "accepted": True,
            "consent_record": record.to_dict(),
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "next_phrase": script.phrase_for_index(len(session.samples)),
        }

    def recover_enrollment(
        self,
        *,
        session_id: str,
        recovery_token: str,
        authenticated_user: str,
    ) -> dict[str, Any]:
        """Resume an interrupted in-flight enrollment session."""
        session = self._require_session(session_id, authenticated_user)
        recoverable = {
            EnrollmentStatus.AWAITING_CONSENT,
            EnrollmentStatus.COLLECTING,
            EnrollmentStatus.VALIDATING,
            EnrollmentStatus.VERIFYING,
            EnrollmentStatus.BUILDING_PROFILE,
        }
        if session.status not in recoverable:
            raise VoiceEnrollmentError(
                f"Cannot recover enrollment in state {session.status.value}",
                code="invalid_state",
            )
        if not session.recovery_token or session.recovery_token != recovery_token:
            raise VoiceEnrollmentError(
                "Invalid enrollment recovery token",
                code="invalid_recovery_token",
            )
        age = (_utc_now() - session.updated_at).total_seconds()
        if age > self._config.recovery_ttl_seconds:
            self._set_workflow(
                session,
                ProductionEnrollmentState.FAILED,
                reason="recovery_ttl_expired",
                force=True,
            )
            session.status = EnrollmentStatus.FAILED
            session.failure_reason = "recovery_ttl_expired"
            self._store.save_session(session)
            self._cleanup_temp(session.session_id)
            self._sync_workspace(session, clear_when_idle=True)
            self._audit(
                "recovery_expired",
                user_id=session.user_id,
                session_id=session.session_id,
                workflow_state=session.workflow_state,
                attempt_number=session.attempt_number,
            )
            raise VoiceEnrollmentError(
                "Enrollment recovery window expired",
                code="recovery_expired",
            )
        # Enter RECOVERY then restore prior productive state.
        prior_workflow = session.workflow_state
        self._set_workflow(
            session,
            ProductionEnrollmentState.RECOVERY,
            reason="recovery_requested",
            force=True,
            metadata={"prior_workflow_state": prior_workflow},
        )
        # Normalize transient VALIDATING back to COLLECTING after crash.
        if session.status == EnrollmentStatus.VALIDATING:
            session.status = EnrollmentStatus.COLLECTING
        restored = (
            ProductionEnrollmentState.WAITING_CONSENT
            if not session.consent_given
            else (
                ProductionEnrollmentState.VERIFYING
                if session.status == EnrollmentStatus.VERIFYING
                else ProductionEnrollmentState.READY_TO_RECORD
            )
        )
        self._set_workflow(
            session,
            restored,
            reason="recovery_restored",
        )
        if restored == ProductionEnrollmentState.READY_TO_RECORD:
            session.status = EnrollmentStatus.COLLECTING
        self._store.save_session(session)
        self._sync_workspace(session)
        self._audit(
            "enrollment_recovered",
            user_id=session.user_id,
            session_id=session.session_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
        )
        script = get_enrollment_script(session.script_id)
        logger.info(
            "VOICE_ENROLLMENT_RECOVERED session=%s user=%s status=%s samples=%d workflow=%s",
            session.session_id,
            session.user_id,
            session.status.value,
            len(session.samples),
            session.workflow_state,
        )
        emit_voice_diagnostic(
            "VOICE_ENROLLMENT_RECOVERED",
            session_id=session.session_id,
            user_id=session.user_id,
            status=session.status.value,
            samples=len(session.samples),
        )
        return {
            "ok": True,
            "recovered": True,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "script": script.to_dict(),
            "next_phrase": (
                script.phrase_for_index(len(session.samples))
                if session.consent_given
                else None
            ),
            "consent_required": not session.consent_given,
        }

    def submit_sample(
        self,
        *,
        session_id: str,
        audio_bytes: bytes,
        authenticated_user: str,
    ) -> dict[str, Any]:
        """Validate and accept one enrollment sample (raw audio transient)."""
        t0 = time.perf_counter()
        session = self._require_session(session_id, authenticated_user)
        if session.status == EnrollmentStatus.AWAITING_CONSENT or (
            self._config.require_consent and not session.consent_given
        ):
            raise VoiceEnrollmentError(
                "Consent is required before submitting enrollment samples.",
                code="consent_required",
            )
        if session.status not in {
            EnrollmentStatus.COLLECTING,
            EnrollmentStatus.VALIDATING,
        }:
            raise VoiceEnrollmentError(
                f"Cannot submit samples in state {session.status.value}",
                code="invalid_state",
            )
        if len(session.samples) >= session.max_samples:
            raise VoiceEnrollmentError(
                "Maximum sample count reached",
                code=SampleRejectReason.LIMIT_REACHED.value,
            )

        session.status = EnrollmentStatus.VALIDATING
        self._set_workflow(
            session,
            ProductionEnrollmentState.RECORDING,
            reason="sample_validation_started",
            force=session.workflow_state
            in {
                ProductionEnrollmentState.READY_TO_RECORD.value,
                ProductionEnrollmentState.RECORDING.value,
                ProductionEnrollmentState.CONSENT_GRANTED.value,
            },
        )
        self._store.save_session(session)
        self._sync_workspace(session)

        temp_path: Path | None = None
        try:
            temp_path = self._write_temp_audio(session.session_id, audio_bytes)
            fingerprints = [s.feature_fingerprint for s in session.samples]
            validation = validate_enrollment_sample(
                audio_bytes,
                config=self._config,
                existing_fingerprints=fingerprints,
            )
            session.last_quality_metrics = validation.production_metrics
            logger.info(
                "VOICE_SAMPLE_RECEIVED session=%s user=%s bytes=%d",
                session.session_id,
                session.user_id,
                len(audio_bytes),
            )
            if not validation.accepted:
                session.status = EnrollmentStatus.COLLECTING
                self._set_workflow(
                    session,
                    ProductionEnrollmentState.READY_TO_RECORD,
                    reason="sample_rejected",
                    force=True,
                )
                session.quality_status = (
                    validation.reject_code.value
                    if validation.reject_code
                    else "rejected"
                )
                session.processing_latency_ms = (time.perf_counter() - t0) * 1000.0
                self._store.save_session(session)
                self._sync_workspace(session)
                self._audit(
                    "sample_rejected",
                    user_id=session.user_id,
                    session_id=session.session_id,
                    workflow_state=session.workflow_state,
                    attempt_number=session.attempt_number,
                    detail=validation.reject_code.value if validation.reject_code else None,
                    metadata={"quality_score": validation.quality_score},
                )
                logger.info(
                    "VOICE_SAMPLE_REJECTED session=%s user=%s reason=%s",
                    session.session_id,
                    session.user_id,
                    validation.reject_code.value if validation.reject_code else "unknown",
                )
                return {
                    "ok": False,
                    "accepted": False,
                    "validation": validation.to_dict(),
                    "session": session.to_public_dict(),
                    "workflow": self._workflow_snapshot(session).to_dict(),
                }

            from voice.embedding_provider import get_embedding_provider
            from voice.enrollment_quality import score_session_quality

            provider = get_embedding_provider()
            embedding = provider.extract(audio_bytes)
            fingerprint = validation.feature_fingerprint or feature_fingerprint(
                embedding
            )
            record = EnrollmentSampleRecord(
                sample_id=str(uuid4()),
                quality_score=validation.quality_score,
                duration_seconds=validation.duration_seconds,
                feature_fingerprint=fingerprint,
                embedding=embedding,
                phrase_index=len(session.samples),
            )
            session.samples.append(record)
            quality = score_session_quality(
                sample_scores=[s.quality_score for s in session.samples],
                embeddings=[list(s.embedding) for s in session.samples],
                required_samples=session.required_samples,
                embedding_version=provider.embedding_version,
            )
            session.aggregate_quality_score = quality.aggregate_score
            session.quality_status = "ok"
            session.status = EnrollmentStatus.COLLECTING
            self._set_workflow(
                session,
                ProductionEnrollmentState.READY_TO_RECORD,
                reason="sample_accepted",
                force=True,
            )
            session.processing_latency_ms = (time.perf_counter() - t0) * 1000.0
            self._store.save_session(session)
            self._sync_workspace(session)
            self._audit(
                "sample_accepted",
                user_id=session.user_id,
                session_id=session.session_id,
                workflow_state=session.workflow_state,
                attempt_number=session.attempt_number,
                metadata={
                    "samples_collected": len(session.samples),
                    "quality_score": validation.quality_score,
                },
            )
            script = get_enrollment_script(session.script_id)
            logger.info(
                "VOICE_SAMPLE_ACCEPTED session=%s user=%s count=%d quality=%.3f",
                session.session_id,
                session.user_id,
                len(session.samples),
                validation.quality_score,
            )
            return {
                "ok": True,
                "accepted": True,
                "validation": validation.to_dict(),
                "session": session.to_public_dict(),
                "workflow": self._workflow_snapshot(session).to_dict(),
                "session_quality": quality.to_dict(),
                "next_phrase": script.phrase_for_index(len(session.samples)),
                "ready_to_finish": quality.ready_to_finish,
            }
        finally:
            if temp_path is not None:
                self._delete_temp_file(temp_path)

    def validate_sample(
        self,
        *,
        audio_bytes: bytes,
        existing_fingerprints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Dry-run sample validation without mutating enrollment state."""
        result = validate_enrollment_sample(
            audio_bytes,
            config=self._config,
            existing_fingerprints=existing_fingerprints,
        )
        return result.to_dict()

    def finish_enrollment(
        self,
        *,
        session_id: str,
        authenticated_user: str,
    ) -> dict[str, Any]:
        """Build an inactive pending profile from collected samples."""
        session = self._require_session(session_id, authenticated_user)
        if session.status not in {
            EnrollmentStatus.COLLECTING,
            EnrollmentStatus.BUILDING_PROFILE,
        }:
            raise VoiceEnrollmentError(
                f"Cannot finish enrollment in state {session.status.value}",
                code="invalid_state",
            )
        if len(session.samples) < session.required_samples:
            raise VoiceEnrollmentError(
                f"Need at least {session.required_samples} samples "
                f"(have {len(session.samples)})",
                code="insufficient_samples",
            )

        session.status = EnrollmentStatus.BUILDING_PROFILE
        self._store.save_session(session)
        self._sync_workspace(session)
        logger.info(
            "VOICE_PROFILE_BUILD_STARTED session=%s user=%s samples=%d",
            session.session_id,
            session.user_id,
            len(session.samples),
        )

        quality = sum(s.quality_score for s in session.samples) / len(session.samples)
        embeddings = [list(s.embedding) for s in session.samples]
        from voice.embedding_provider import get_embedding_provider
        from voice.enrollment_quality import (
            detect_cross_user_duplicates,
            detect_same_user_near_duplicate,
            score_embedding_quality,
            score_session_quality,
        )

        provider = get_embedding_provider()
        embedding_reports = [
            score_embedding_quality(emb, embedding_version=provider.embedding_version)
            for emb in embeddings
        ]
        avg_embedding_quality = (
            sum(r.score for r in embedding_reports) / len(embedding_reports)
            if embedding_reports
            else 0.0
        )
        session_quality = score_session_quality(
            sample_scores=[s.quality_score for s in session.samples],
            embeddings=embeddings,
            required_samples=session.required_samples,
            embedding_version=provider.embedding_version,
        )
        session.aggregate_quality_score = session_quality.aggregate_score
        other_profiles = [
            p
            for p in self._store.iter_profiles()
            if p.user_id != session.user_id and p.active
        ]
        dup = detect_cross_user_duplicates(
            user_id=session.user_id,
            embeddings=embeddings,
            candidates=other_profiles,
            embedding_version=provider.embedding_version,
        )
        if dup.is_duplicate:
            self._set_workflow(
                session,
                ProductionEnrollmentState.FAILED,
                reason="cross_user_duplicate_detected",
                force=True,
            )
            session.status = EnrollmentStatus.FAILED
            session.failure_reason = "cross_user_duplicate_detected"
            self._store.save_session(session)
            self._sync_workspace(session)
            self._audit(
                "enrollment_failed",
                user_id=session.user_id,
                session_id=session.session_id,
                workflow_state=session.workflow_state,
                attempt_number=session.attempt_number,
                detail="cross_user_duplicate_detected",
            )
            logger.warning(
                "VOICE_ENROLLMENT_DUPLICATE_BLOCKED session=%s user=%s matches=%d",
                session.session_id,
                session.user_id,
                len(dup.matches),
            )
            return {
                "ok": False,
                "activated": False,
                "session": session.to_public_dict(),
                "workflow": self._workflow_snapshot(session).to_dict(),
                "duplicate_detection": dup.to_dict(),
                "session_quality": session_quality.to_dict(),
                "embedding_quality": {
                    "average": round(avg_embedding_quality, 4),
                    "reports": [r.to_dict() for r in embedding_reports],
                },
                "error": "cross_user_duplicate_detected",
                "message": "Empreinte vocale trop proche d'un autre profil actif.",
            }

        existing_own = self._store.get_active_profile(session.user_id)
        same_user_dup = detect_same_user_near_duplicate(
            embeddings=embeddings,
            existing_profile=existing_own,
            embedding_version=provider.embedding_version,
            threshold=self._config.same_user_duplicate_threshold,
        )

        profile_version = self._store.next_profile_version(session.user_id)
        profile = SpeakerIdentityProfile.create(
            user_id=session.user_id,
            display_name=session.user_id,
            status=EnrollmentStatus.VERIFYING,
            profile_version=profile_version,
        )
        profile.embeddings = embeddings
        profile.sample_count = len(profile.embeddings)
        profile.embedding_version = provider.embedding_version
        profile.quality_score = (
            min(quality, avg_embedding_quality) if avg_embedding_quality else quality
        )
        profile.confidence = 0.0
        profile.active = False
        profile.enrollment_fingerprints = [
            s.feature_fingerprint for s in session.samples
        ]
        profile.replaces_profile_id = session.replacing_profile_id
        self._store.create_profile(profile)

        session.pending_profile_id = profile.profile_id
        session.status = EnrollmentStatus.VERIFYING
        self._set_workflow(
            session,
            ProductionEnrollmentState.VERIFYING,
            reason="profile_built_awaiting_verification",
            force=True,
        )
        session.verification_status = "awaiting_verification_sample"
        session.embedding_version = provider.embedding_version
        self._store.save_session(session)
        self._sync_workspace(session)
        self._audit(
            "profile_built",
            user_id=session.user_id,
            session_id=session.session_id,
            profile_id=profile.profile_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
            metadata={"profile_version": profile.profile_version},
        )
        logger.info(
            "VOICE_PROFILE_BUILT session=%s user=%s profile=%s active=%s version=%d",
            session.session_id,
            session.user_id,
            profile.profile_id,
            False,
            profile.profile_version,
        )
        return {
            "ok": True,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "profile": profile.to_public_dict(),
            "duplicate_detection": dup.to_dict(),
            "same_user_near_duplicate": same_user_dup.to_dict(),
            "replacement_plan": {
                "action": "atomic_replace" if session.replacing_profile_id else "activate_new",
                "existing_profile_id": session.replacing_profile_id,
                "new_profile_id": profile.profile_id,
                "revoke_old": bool(session.replacing_profile_id),
                "near_duplicate_update": same_user_dup.is_duplicate,
                "profile_version": profile.profile_version,
            },
            "session_quality": session_quality.to_dict(),
            "embedding_quality": {
                "average": round(avg_embedding_quality, 4),
                "reports": [r.to_dict() for r in embedding_reports],
                "language_independent": True,
            },
            "message": "Profil créé — une vérification vocale est requise avant activation.",
        }

    def verify_enrollment(
        self,
        *,
        session_id: str,
        audio_bytes: bytes,
        authenticated_user: str,
    ) -> dict[str, Any]:
        """Verify with a fresh sample; activate only on success."""
        session = self._require_session(session_id, authenticated_user)
        if session.status != EnrollmentStatus.VERIFYING:
            raise VoiceEnrollmentError(
                f"Cannot verify in state {session.status.value}",
                code="invalid_state",
            )
        if not session.pending_profile_id:
            raise VoiceEnrollmentError(
                "No pending profile to verify",
                code="missing_pending_profile",
            )
        profile = self._store.get_profile(session.pending_profile_id)
        if profile is None:
            raise VoiceEnrollmentError(
                "Pending profile missing",
                code="missing_pending_profile",
            )

        logger.info(
            "VOICE_ENROLLMENT_VERIFICATION_STARTED session=%s user=%s profile=%s",
            session.session_id,
            session.user_id,
            profile.profile_id,
        )

        temp_path: Path | None = None
        try:
            temp_path = self._write_temp_audio(session.session_id, audio_bytes)
            validation = validate_enrollment_sample(
                audio_bytes,
                config=self._config,
                existing_fingerprints=profile.enrollment_fingerprints,
            )
            if not validation.accepted:
                # Duplicate of enrollment set or bad quality — not a verification pass.
                if validation.reject_code == SampleRejectReason.DUPLICATE:
                    return self._fail_verification(
                        session,
                        profile,
                        EnrollmentVerificationResult(
                            matched_identity=None,
                            confidence=0.0,
                            threshold=self._config.min_enrollment_confidence,
                            outcome=VerificationOutcome.FAILED,
                            reason="verification_sample_reused_from_enrollment",
                        ),
                    )
                return self._fail_verification(
                    session,
                    profile,
                    EnrollmentVerificationResult(
                        matched_identity=None,
                        confidence=0.0,
                        threshold=self._config.min_enrollment_confidence,
                        outcome=VerificationOutcome.FAILED,
                        reason=validation.reject_code.value
                        if validation.reject_code
                        else "verification_sample_rejected",
                    ),
                )

            probe = extract_voice_features(audio_bytes)
            # Rebuild thresholds from live config (tests may mutate thresholds).
            pipeline = EnrollmentVerificationPipeline(
                VerificationThresholds.from_config(self._config)
            )
            pipeline_result = pipeline.score_probe(
                probe_embedding=probe,
                profile_embeddings=profile.embeddings,
                expected_user_id=session.user_id,
                profile_embedding_version=profile.embedding_version,
                retries_used=session.verification_retries,
                probe_quality=validation.quality_score,
            )
            result = pipeline_result.verification
            session.last_verification_confidence = result.confidence

            if result.outcome == VerificationOutcome.PASSED:
                return self._complete_verification(
                    session, profile, result, pipeline=pipeline_result.to_dict()
                )

            return self._fail_verification(
                session,
                profile,
                result,
                retryable=pipeline_result.retry_allowed
                or (
                    result.outcome
                    in {
                        VerificationOutcome.NEEDS_CONFIRMATION,
                        VerificationOutcome.UNKNOWN,
                        VerificationOutcome.AMBIGUOUS,
                    }
                    and session.verification_retries + 1
                    < self._config.max_verification_retries
                ),
                pipeline=pipeline_result.to_dict(),
            )
        finally:
            if temp_path is not None:
                self._delete_temp_file(temp_path)

    def cancel_enrollment(
        self,
        *,
        session_id: str,
        authenticated_user: str,
    ) -> dict[str, Any]:
        session = self._require_session(session_id, authenticated_user)
        if session.pending_profile_id:
            pending = self._store.get_profile(session.pending_profile_id)
            if pending is not None and not pending.active:
                pending.enrollment_status = EnrollmentStatus.CANCELLED
                pending.failure_reason = "cancelled"
                pending.active = False
                self._store.update_profile(pending)
        self._set_workflow(
            session,
            ProductionEnrollmentState.CANCELLED,
            reason="cancelled_by_user",
            force=True,
        )
        session.status = EnrollmentStatus.CANCELLED
        session.failure_reason = "cancelled"
        session.verification_status = "cancelled"
        self._store.save_session(session)
        self._cleanup_temp(session.session_id)
        self._sync_workspace(session, clear_when_idle=True)
        self._audit(
            "enrollment_cancelled",
            user_id=session.user_id,
            session_id=session.session_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
        )
        logger.info(
            "VOICE_ENROLLMENT_CANCELLED session=%s user=%s",
            session.session_id,
            session.user_id,
        )
        return {
            "ok": True,
            "cancelled": True,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
        }

    def revoke_profile(
        self,
        *,
        user_id: str,
        authenticated_user: str,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        target = SessionManager.normalize_user(user_id)
        auth = SessionManager.normalize_user(authenticated_user)
        if target is None or auth is None or auth != target:
            raise VoiceEnrollmentError(
                "Revocation requires matching authorized user.",
                code="unauthorized",
            )
        profile = None
        if profile_id:
            profile = self._store.get_profile(profile_id)
        if profile is None:
            profile = self._store.get_active_profile(target)
        if profile is None:
            raise VoiceEnrollmentError(
                "No profile to revoke",
                code="not_found",
            )
        if profile.user_id != target:
            raise VoiceEnrollmentError(
                "Profile does not belong to user",
                code="unauthorized",
            )
        revoked = self._store.revoke_profile(profile.profile_id)
        logger.info(
            "VOICE_PROFILE_REVOKED user=%s profile=%s",
            target,
            revoked.profile_id,
        )
        self._audit(
            "profile_revoked",
            user_id=target,
            profile_id=revoked.profile_id,
            detail="explicit_revocation",
            metadata={"profile_version": revoked.profile_version},
        )
        self._sync_workspace_idle(target)
        return {"ok": True, "profile": revoked.to_public_dict()}

    def get_status(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        authenticated_user: str | None = None,
    ) -> dict[str, Any]:
        """Safe enrollment status for API / workspace consumers."""
        session = None
        if session_id:
            session = self._store.get_session(session_id)
            if (
                session is not None
                and authenticated_user
                and SessionManager.normalize_user(authenticated_user) != session.user_id
            ):
                raise VoiceEnrollmentError("Forbidden", code="unauthorized")
        elif user_id:
            normalized = SessionManager.normalize_user(user_id)
            if normalized:
                session = self._store.get_active_session_for_user(normalized)

        profiles = self._store.list_safe_profiles(
            user_id=SessionManager.normalize_user(user_id) if user_id else None
        )
        active = None
        if user_id:
            normalized = SessionManager.normalize_user(user_id)
            if normalized:
                active_profile = self._store.get_active_profile(normalized)
                active = active_profile.to_public_dict() if active_profile else None

        history: list[dict[str, Any]] = []
        if user_id:
            normalized_history = SessionManager.normalize_user(user_id)
            if normalized_history:
                history = [
                    s.to_public_dict()
                    for s in self._store.list_sessions_for_user(normalized_history)
                ]

        return {
            "config": self._config.to_dict(),
            "session": session.to_public_dict() if session else None,
            "workflow": self._workflow_snapshot(session).to_dict() if session else None,
            "active_profile": active,
            "profiles": profiles,
            "enrollment_history": history,
            "audit_history": self._store.list_audit_history(
                user_id=SessionManager.normalize_user(user_id) if user_id else None,
                session_id=session_id,
                limit=50,
            ),
            "verification_thresholds": VerificationThresholds.from_config(
                self._config
            ).to_dict(),
            "available_scripts": list_enrollment_scripts(),
            "workspace": self._workspace_snapshot(session),
        }

    # --- internals ----------------------------------------------------

    def _audit(
        self,
        event_type: str,
        *,
        user_id: str,
        session_id: str | None = None,
        profile_id: str | None = None,
        workflow_state: str | None = None,
        attempt_number: int = 1,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = make_audit_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            profile_id=profile_id,
            workflow_state=workflow_state,
            attempt_number=attempt_number,
            detail=detail,
            metadata=metadata,
        )
        self._store.append_audit(event)
        emit_voice_diagnostic(
            f"VOICE_ENROLLMENT_AUDIT_{event_type.upper()}",
            user_id=user_id,
            session_id=session_id,
            workflow_state=workflow_state,
        )

    def _current_workflow(self, session: EnrollmentSession) -> ProductionEnrollmentState:
        try:
            return ProductionEnrollmentState(session.workflow_state)
        except ValueError:
            return legacy_to_production(session.status)

    def _set_workflow(
        self,
        session: EnrollmentSession,
        target: ProductionEnrollmentState,
        *,
        reason: str,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        current = self._current_workflow(session)
        self._workflow.load_history(session.workflow_transitions)
        event = self._workflow.transition(
            current,
            target,
            reason=reason,
            attempt_number=session.attempt_number,
            metadata=metadata,
            force=force,
        )
        session.workflow_state = target.value
        session.workflow_transitions.append(event.to_dict())

    def _workflow_snapshot(self, session: EnrollmentSession):
        self._workflow.load_history(session.workflow_transitions)
        return self._workflow.snapshot(
            workflow_state=self._current_workflow(session),
            legacy_status=session.status,
            attempt_number=session.attempt_number,
        )

    def _require_session(
        self, session_id: str, authenticated_user: str
    ) -> EnrollmentSession:
        auth = SessionManager.normalize_user(authenticated_user)
        if auth is None:
            raise VoiceEnrollmentError(
                "Enrollment requires an authenticated authorized user.",
                code="unauthorized",
            )
        session = self._store.get_session(session_id)
        if session is None:
            raise VoiceEnrollmentError("Enrollment session not found", code="not_found")
        if session.user_id != auth:
            raise VoiceEnrollmentError(
                "Enrollment session belongs to another user",
                code="unauthorized",
            )
        return session

    def _complete_verification(
        self,
        session: EnrollmentSession,
        profile: SpeakerIdentityProfile,
        result: EnrollmentVerificationResult,
        *,
        pipeline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile.confidence = result.confidence
        profile.last_verified_at = _utc_now()
        profile.failure_reason = None
        self._store.update_profile(profile)

        old_id = session.replacing_profile_id
        activated = self._store.replace_active_profile(
            new_profile_id=profile.profile_id,
            old_profile_id=old_id,
        )
        self._set_workflow(
            session,
            ProductionEnrollmentState.SUCCESS,
            reason="verification_passed",
            force=True,
        )
        session.status = EnrollmentStatus.ENROLLED
        session.verification_status = "verified"
        session.failure_reason = None
        session.last_verification_confidence = result.confidence
        self._store.save_session(session)
        self._cleanup_temp(session.session_id)
        self._sync_workspace(session, clear_when_idle=True)
        self._audit(
            "enrollment_success",
            user_id=session.user_id,
            session_id=session.session_id,
            profile_id=activated.profile_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
            metadata={
                "confidence": result.confidence,
                "profile_version": activated.profile_version,
            },
        )
        logger.info(
            "VOICE_ENROLLMENT_VERIFIED session=%s user=%s profile=%s confidence=%.4f",
            session.session_id,
            session.user_id,
            activated.profile_id,
            result.confidence,
        )
        logger.info(
            "VOICE_PROFILE_ACTIVATED user=%s profile=%s",
            activated.user_id,
            activated.profile_id,
        )
        return {
            "ok": True,
            "activated": True,
            "verification": result.to_dict(),
            "verification_pipeline": pipeline,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "profile": activated.to_public_dict(),
        }

    def _fail_verification(
        self,
        session: EnrollmentSession,
        profile: SpeakerIdentityProfile,
        result: EnrollmentVerificationResult,
        *,
        retryable: bool = False,
        pipeline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session.verification_retries += 1
        session.verification_status = result.outcome.value
        session.failure_reason = result.reason
        session.last_verification_confidence = result.confidence

        # Never leave a partial active profile.
        profile.active = False
        profile.failure_reason = result.reason
        if (
            retryable
            and session.verification_retries < self._config.max_verification_retries
        ):
            profile.enrollment_status = EnrollmentStatus.VERIFYING
            session.status = EnrollmentStatus.VERIFYING
            self._set_workflow(
                session,
                ProductionEnrollmentState.VERIFYING,
                reason=f"verification_retry:{result.reason}",
                force=True,
            )
            self._store.update_profile(profile)
            self._store.save_session(session)
            self._sync_workspace(session)
            self._audit(
                "verification_retry",
                user_id=session.user_id,
                session_id=session.session_id,
                profile_id=profile.profile_id,
                workflow_state=session.workflow_state,
                attempt_number=session.attempt_number,
                detail=result.reason,
                metadata={"confidence": result.confidence},
            )
            logger.info(
                "VOICE_ENROLLMENT_FAILED session=%s user=%s reason=%s retry=%d",
                session.session_id,
                session.user_id,
                result.reason,
                session.verification_retries,
            )
            return {
                "ok": False,
                "activated": False,
                "retry_allowed": True,
                "verification": result.to_dict(),
                "verification_pipeline": pipeline,
                "session": session.to_public_dict(),
                "workflow": self._workflow_snapshot(session).to_dict(),
                "profile": profile.to_public_dict(),
            }

        profile.enrollment_status = EnrollmentStatus.FAILED
        session.status = EnrollmentStatus.FAILED
        self._set_workflow(
            session,
            ProductionEnrollmentState.FAILED,
            reason=result.reason,
            force=True,
        )
        self._store.update_profile(profile)
        self._store.save_session(session)
        self._cleanup_temp(session.session_id)
        self._sync_workspace(session, clear_when_idle=True)
        self._audit(
            "enrollment_failed",
            user_id=session.user_id,
            session_id=session.session_id,
            profile_id=profile.profile_id,
            workflow_state=session.workflow_state,
            attempt_number=session.attempt_number,
            detail=result.reason,
            metadata={"confidence": result.confidence},
        )
        logger.info(
            "VOICE_ENROLLMENT_FAILED session=%s user=%s reason=%s final=true",
            session.session_id,
            session.user_id,
            result.reason,
        )
        return {
            "ok": False,
            "activated": False,
            "retry_allowed": False,
            "verification": result.to_dict(),
            "verification_pipeline": pipeline,
            "session": session.to_public_dict(),
            "workflow": self._workflow_snapshot(session).to_dict(),
            "profile": profile.to_public_dict(),
        }

    def _workspace_snapshot(
        self, session: EnrollmentSession | None
    ) -> dict[str, Any]:
        if session is None:
            return {
                "voice_enrollment_status": EnrollmentStatus.NOT_ENROLLED.value,
                "voice_enrollment_workflow": None,
                "voice_enrollment_user": None,
                "voice_samples_collected": 0,
                "voice_samples_required": self._config.min_sample_count,
                "voice_quality_status": None,
                "voice_verification_status": None,
            }
        return {
            "voice_enrollment_status": session.status.value,
            "voice_enrollment_workflow": session.workflow_state,
            "voice_enrollment_user": session.user_id,
            "voice_samples_collected": len(session.samples),
            "voice_samples_required": session.required_samples,
            "voice_quality_status": session.quality_status,
            "voice_verification_status": session.verification_status,
        }

    def _sync_workspace(
        self,
        session: EnrollmentSession,
        *,
        clear_when_idle: bool = False,
    ) -> None:
        if self._state_manager is None:
            return
        payload = self._workspace_snapshot(session)
        if clear_when_idle and session.status in {
            EnrollmentStatus.ENROLLED,
            EnrollmentStatus.FAILED,
            EnrollmentStatus.CANCELLED,
            EnrollmentStatus.REVOKED,
        }:
            # Keep terminal status briefly visible, then allow idle fields.
            pass
        try:
            self._state_manager.update(payload)
        except Exception:
            logger.exception("Failed to mirror voice enrollment onto WorkspaceState")

    def _sync_workspace_idle(self, user_id: str) -> None:
        if self._state_manager is None:
            return
        try:
            self._state_manager.update(
                {
                    "voice_enrollment_status": EnrollmentStatus.REVOKED.value,
                    "voice_enrollment_user": user_id,
                    "voice_samples_collected": 0,
                    "voice_samples_required": self._config.min_sample_count,
                    "voice_quality_status": None,
                    "voice_verification_status": "revoked",
                }
            )
        except Exception:
            logger.exception("Failed to mirror voice revoke onto WorkspaceState")

    def _ensure_temp_root(self) -> Path:
        if self._temp_root is None:
            base = Path(tempfile.gettempdir()) / "titan_voice_enrollment"
            self._temp_root = base
        self._temp_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._temp_root, stat.S_IRWXU)
        except OSError:
            pass
        self._cleanup_abandoned_temp()
        return self._temp_root

    def _write_temp_audio(self, session_id: str, audio_bytes: bytes) -> Path:
        root = self._ensure_temp_root()
        session_dir = root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(session_dir, stat.S_IRWXU)
        except OSError:
            pass
        path = session_dir / f"{uuid4().hex}.bin"
        path.write_bytes(audio_bytes)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return path

    def _delete_temp_file(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
                logger.info("VOICE_TEMP_AUDIO_DELETED path=%s", path.name)
        except OSError:
            logger.warning("Failed to delete temp enrollment audio %s", path.name)

    def _cleanup_temp(self, session_id: str) -> None:
        if self._temp_root is None:
            return
        session_dir = self._temp_root / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.info("VOICE_TEMP_AUDIO_DELETED session=%s", session_id)

    def _cleanup_abandoned_temp(self) -> None:
        if self._temp_root is None or not self._temp_root.exists():
            return
        try:
            for child in self._temp_root.iterdir():
                if not child.is_dir():
                    continue
                # Drop dirs with no matching active session.
                if self._store.get_session(child.name) is None:
                    shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass

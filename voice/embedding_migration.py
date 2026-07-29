# =====================================
# Titan Embedding Migration
# =====================================

"""Safe migration between embedding versions (Phase 20.11).

Existing development histogram profiles must NOT automatically become
production-trusted identities. Migration requires an explicit re-enrollment
path. Real Nolan/Ibrahim enrollment remains deferred until Phase 20.10B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from voice.embedding_provider import (
    DEV_FALLBACK_VERSIONS,
    get_embedding_provider,
    get_embedding_registry,
    is_dev_fallback_version,
    is_production_trusted_version,
)
from voice.enrollment_models import EnrollmentStatus, SpeakerIdentityProfile
from voice.speaker_profile_store import SpeakerProfileStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


class MigrationStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING_REENROLLMENT = "pending_reenrollment"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED_AUTO_TRUST = "blocked_auto_trust"
    FAILED = "failed"


@dataclass
class ProfileMigrationPlan:
    """Per-profile migration / re-enrollment plan (safe metadata only)."""

    profile_id: str
    user_id: str
    from_version: str
    to_version: str
    status: MigrationStatus
    production_trusted_after: bool
    requires_reenrollment: bool
    auto_trust_blocked: bool
    reason: str
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "status": self.status.value,
            "production_trusted_after": self.production_trusted_after,
            "requires_reenrollment": self.requires_reenrollment,
            "auto_trust_blocked": self.auto_trust_blocked,
            "reason": self.reason,
            "created_at": _iso(self.created_at),
        }


@dataclass
class EmbeddingMigrationReport:
    """Store-wide migration assessment (never includes embeddings)."""

    target_version: str
    target_production_trusted: bool
    plans: list[ProfileMigrationPlan] = field(default_factory=list)
    histogram_profiles_blocked_from_auto_trust: int = 0
    reenrollment_required_count: int = 0
    phase_20_10b_deferred: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_version": self.target_version,
            "target_production_trusted": self.target_production_trusted,
            "plans": [p.to_dict() for p in self.plans],
            "histogram_profiles_blocked_from_auto_trust": (
                self.histogram_profiles_blocked_from_auto_trust
            ),
            "reenrollment_required_count": self.reenrollment_required_count,
            "phase_20_10b_deferred": self.phase_20_10b_deferred,
            "auto_promote_histogram_forbidden": True,
        }


class EmbeddingMigrationService:
    """Plan and apply embedding-version migrations without silent trust promotion."""

    def __init__(self, store: SpeakerProfileStore) -> None:
        self._store = store

    def assess(
        self, *, target_provider_id: str | None = None
    ) -> EmbeddingMigrationReport:
        """Build migration plans — histogram never auto-promoted to production trust."""
        registry = get_embedding_registry()
        if target_provider_id:
            target = registry.get(target_provider_id)
        else:
            target = get_embedding_provider()
        target_version = target.embedding_version
        target_trusted = target.is_production_trusted

        self._store.load()
        plans: list[ProfileMigrationPlan] = []
        blocked = 0
        reenroll = 0

        for profile in self._store.iter_profiles():
            if profile.enrollment_status == EnrollmentStatus.REVOKED:
                continue
            from_version = profile.embedding_version or "unknown"
            if from_version == target_version and not is_dev_fallback_version(
                from_version
            ):
                plans.append(
                    ProfileMigrationPlan(
                        profile_id=profile.profile_id,
                        user_id=profile.user_id,
                        from_version=from_version,
                        to_version=target_version,
                        status=MigrationStatus.NOT_REQUIRED,
                        production_trusted_after=target_trusted,
                        requires_reenrollment=False,
                        auto_trust_blocked=False,
                        reason="already_on_target_version",
                    )
                )
                continue

            # Histogram / other dev fallbacks: never auto-trust as production.
            if is_dev_fallback_version(from_version):
                blocked += 1
                reenroll += 1
                plans.append(
                    ProfileMigrationPlan(
                        profile_id=profile.profile_id,
                        user_id=profile.user_id,
                        from_version=from_version,
                        to_version=target_version,
                        status=MigrationStatus.BLOCKED_AUTO_TRUST,
                        production_trusted_after=False,
                        requires_reenrollment=True,
                        auto_trust_blocked=True,
                        reason=(
                            "histogram_dev_fallback_cannot_auto_become_production"
                            if from_version in DEV_FALLBACK_VERSIONS
                            else "dev_fallback_requires_reenrollment"
                        ),
                    )
                )
                continue

            if from_version != target_version:
                reenroll += 1
                plans.append(
                    ProfileMigrationPlan(
                        profile_id=profile.profile_id,
                        user_id=profile.user_id,
                        from_version=from_version,
                        to_version=target_version,
                        status=MigrationStatus.PENDING_REENROLLMENT,
                        production_trusted_after=target_trusted,
                        requires_reenrollment=True,
                        auto_trust_blocked=False,
                        reason="embedding_version_change_requires_reenrollment",
                    )
                )
                continue

            plans.append(
                ProfileMigrationPlan(
                    profile_id=profile.profile_id,
                    user_id=profile.user_id,
                    from_version=from_version,
                    to_version=target_version,
                    status=MigrationStatus.NOT_REQUIRED,
                    production_trusted_after=is_production_trusted_version(
                        from_version
                    ),
                    requires_reenrollment=False,
                    auto_trust_blocked=False,
                    reason="compatible",
                )
            )

        return EmbeddingMigrationReport(
            target_version=target_version,
            target_production_trusted=target_trusted,
            plans=plans,
            histogram_profiles_blocked_from_auto_trust=blocked,
            reenrollment_required_count=reenroll,
            phase_20_10b_deferred=True,
        )

    def mark_requires_reenrollment(
        self, profile_id: str, *, reason: str = "migration_reenrollment_required"
    ) -> SpeakerIdentityProfile:
        """Deactivate a profile and mark it for explicit re-enrollment."""
        profile = self._store.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"Unknown profile {profile_id}")
        # Do not revoke permanently — deactivate so recognition stops until re-enroll.
        if profile.active:
            self._store.deactivate_profile(profile_id)
            profile = self._store.get_profile(profile_id) or profile
        profile.failure_reason = reason
        profile.updated_at = _utc_now()
        # Clear active trust without deleting history.
        profile.active = False
        self._store.update_profile(profile)
        return profile

    def apply_pending_deactivations(
        self, report: EmbeddingMigrationReport | None = None
    ) -> EmbeddingMigrationReport:
        """Deactivate all profiles that require re-enrollment (explicit path)."""
        assessment = report or self.assess()
        for plan in assessment.plans:
            if plan.requires_reenrollment and plan.auto_trust_blocked:
                try:
                    self.mark_requires_reenrollment(
                        plan.profile_id, reason=plan.reason
                    )
                    plan.status = MigrationStatus.PENDING_REENROLLMENT
                except ValueError:
                    plan.status = MigrationStatus.FAILED
        return assessment

    def public_status(self) -> dict[str, Any]:
        """Safe migration status for diagnostics."""
        report = self.assess()
        return {
            "migration": report.to_dict(),
            "histogram_auto_trust_forbidden": True,
            "phase_20_10b_real_enrollment_deferred": True,
        }

# =====================================
# Titan Voice Identity Security Boundary
# =====================================

"""Speaker recognition must not authorize high-risk actions (Phase 20.11 / 20.12).

Voice identity may select the correct user context only after verification
succeeds. Unknown or ambiguous speakers must never receive another user's
personal context or memories. Existing auth/authorization systems remain
authoritative for destructive, financial, administrative, and other
high-risk operations.

Phase 20.12 separates CLAIMED_IDENTITY (spoken/UI confirmation) from
VERIFIED_IDENTITY (biometric verification policy success). Saying
« je suis Nolan » must never automatically become biometrically VERIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from voice.enrollment_models import RecognitionBand
from voice.speaker_verification import (
    SpeakerVerificationResult,
    VerificationDecision,
)


class IdentityAssertionKind(str, Enum):
    """How an identity label was established."""

    # Spoken or UI confirmation — never biometrically verified by itself.
    CLAIMED_IDENTITY = "claimed_identity"
    # Biometric verification policy succeeded.
    VERIFIED_IDENTITY = "verified_identity"
    # No usable identity.
    UNKNOWN = "unknown"


class IdentityActionClass(str, Enum):
    """Action classes relative to speaker-identity authorization."""

    # Safe: bind conversational user context / memory after verification.
    CONTEXT_SELECTION = "context_selection"
    # Explicitly forbidden for voice-identity alone.
    DESTRUCTIVE = "destructive"
    FINANCIAL = "financial"
    ADMINISTRATIVE = "administrative"
    HIGH_RISK = "high_risk"
    # Auth systems own these — voice may never elevate.
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"


# Actions that speaker recognition must NEVER authorize by itself.
VOICE_IDENTITY_FORBIDDEN_ACTIONS: frozenset[IdentityActionClass] = frozenset(
    {
        IdentityActionClass.DESTRUCTIVE,
        IdentityActionClass.FINANCIAL,
        IdentityActionClass.ADMINISTRATIVE,
        IdentityActionClass.HIGH_RISK,
        IdentityActionClass.AUTHENTICATION,
        IdentityActionClass.AUTHORIZATION,
    }
)


@dataclass(frozen=True)
class IdentitySecurityDecision:
    """Safe decision about what voice identity may do."""

    allowed: bool
    action_class: IdentityActionClass
    reason: str
    may_bind_user_context: bool
    may_access_personal_memory: bool
    requires_separate_auth: bool
    assertion_kind: IdentityAssertionKind = IdentityAssertionKind.UNKNOWN
    is_biometrically_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action_class": self.action_class.value,
            "reason": self.reason,
            "may_bind_user_context": self.may_bind_user_context,
            "may_access_personal_memory": self.may_access_personal_memory,
            "requires_separate_auth": self.requires_separate_auth,
            "assertion_kind": self.assertion_kind.value,
            "is_biometrically_verified": self.is_biometrically_verified,
        }


class IdentitySecurityBoundary:
    """Enforce that voice ID is not an authorization primitive."""

    def evaluate_action(
        self,
        action_class: IdentityActionClass,
        *,
        verification: SpeakerVerificationResult | None = None,
        assertion_kind: IdentityAssertionKind | None = None,
    ) -> IdentitySecurityDecision:
        """Decide whether voice identity may participate in an action class."""
        if action_class in VOICE_IDENTITY_FORBIDDEN_ACTIONS:
            return IdentitySecurityDecision(
                allowed=False,
                action_class=action_class,
                reason="voice_identity_cannot_authorize_high_risk",
                may_bind_user_context=False,
                may_access_personal_memory=False,
                requires_separate_auth=True,
                assertion_kind=assertion_kind or IdentityAssertionKind.UNKNOWN,
                is_biometrically_verified=False,
            )

        if action_class != IdentityActionClass.CONTEXT_SELECTION:
            return IdentitySecurityDecision(
                allowed=False,
                action_class=action_class,
                reason="unknown_action_class",
                may_bind_user_context=False,
                may_access_personal_memory=False,
                requires_separate_auth=True,
                assertion_kind=assertion_kind or IdentityAssertionKind.UNKNOWN,
                is_biometrically_verified=False,
            )

        if assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY:
            # Claimed identity may label the session for UX, but must never
            # unlock personal memory that requires biometric verification.
            return IdentitySecurityDecision(
                allowed=True,
                action_class=action_class,
                reason="claimed_identity_session_label_only",
                may_bind_user_context=True,
                may_access_personal_memory=False,
                requires_separate_auth=False,
                assertion_kind=IdentityAssertionKind.CLAIMED_IDENTITY,
                is_biometrically_verified=False,
            )

        if verification is None:
            return IdentitySecurityDecision(
                allowed=False,
                action_class=action_class,
                reason="verification_required",
                may_bind_user_context=False,
                may_access_personal_memory=False,
                requires_separate_auth=False,
                assertion_kind=assertion_kind or IdentityAssertionKind.UNKNOWN,
                is_biometrically_verified=False,
            )

        return self.evaluate_context_binding(verification)

    def evaluate_context_binding(
        self, verification: SpeakerVerificationResult
    ) -> IdentitySecurityDecision:
        """Allow personal context only after a successful high-confidence match."""
        if (
            verification.decision
            in {VerificationDecision.MATCHED, VerificationDecision.VERIFIED}
            and verification.is_known
        ):
            if verification.recognition_band == RecognitionBand.HIGH:
                return IdentitySecurityDecision(
                    allowed=True,
                    action_class=IdentityActionClass.CONTEXT_SELECTION,
                    reason="verified_high_confidence",
                    may_bind_user_context=True,
                    may_access_personal_memory=True,
                    requires_separate_auth=False,
                    assertion_kind=IdentityAssertionKind.VERIFIED_IDENTITY,
                    is_biometrically_verified=True,
                )
            return IdentitySecurityDecision(
                allowed=False,
                action_class=IdentityActionClass.CONTEXT_SELECTION,
                reason="matched_but_band_insufficient",
                may_bind_user_context=False,
                may_access_personal_memory=False,
                requires_separate_auth=False,
                assertion_kind=IdentityAssertionKind.UNKNOWN,
                is_biometrically_verified=False,
            )

        if verification.decision == VerificationDecision.AMBIGUOUS:
            return IdentitySecurityDecision(
                allowed=False,
                action_class=IdentityActionClass.CONTEXT_SELECTION,
                reason="ambiguous_speaker_blocks_personal_context",
                may_bind_user_context=False,
                may_access_personal_memory=False,
                requires_separate_auth=False,
                assertion_kind=IdentityAssertionKind.UNKNOWN,
                is_biometrically_verified=False,
            )

        return IdentitySecurityDecision(
            allowed=False,
            action_class=IdentityActionClass.CONTEXT_SELECTION,
            reason="unknown_or_rejected_speaker",
            may_bind_user_context=False,
            may_access_personal_memory=False,
            requires_separate_auth=False,
            assertion_kind=IdentityAssertionKind.UNKNOWN,
            is_biometrically_verified=False,
        )

    def evaluate_assertion(
        self, assertion_kind: IdentityAssertionKind
    ) -> IdentitySecurityDecision:
        """Evaluate a claimed vs verified assertion without a probe score."""
        return self.evaluate_action(
            IdentityActionClass.CONTEXT_SELECTION,
            assertion_kind=assertion_kind,
        )

    def assert_not_authorization(self, *, source: str = "voice_identity") -> dict[str, Any]:
        """Public statement that voice recognition is not authz."""
        return {
            "source": source,
            "is_authentication": False,
            "is_authorization": False,
            "may_authorize_destructive": False,
            "may_authorize_financial": False,
            "may_authorize_administrative": False,
            "may_authorize_high_risk": False,
            "context_selection_only_after_verification": True,
            "unknown_never_receives_foreign_memory": True,
            "preserves_existing_auth_systems": True,
            "claimed_identity_is_not_verified": True,
            "personal_memory_requires_verified_identity": True,
        }


def voice_identity_may_bind_context(verification: SpeakerVerificationResult) -> bool:
    """Convenience: True only when personal user context may be bound."""
    return IdentitySecurityBoundary().evaluate_context_binding(verification).may_bind_user_context


def voice_identity_may_access_personal_memory(
    *,
    assertion_kind: IdentityAssertionKind | None = None,
    verification: SpeakerVerificationResult | None = None,
) -> bool:
    """True only for biometrically VERIFIED identity — never for CLAIMED."""
    boundary = IdentitySecurityBoundary()
    if assertion_kind == IdentityAssertionKind.CLAIMED_IDENTITY:
        return False
    if assertion_kind == IdentityAssertionKind.VERIFIED_IDENTITY and verification is None:
        return True
    if verification is not None:
        return boundary.evaluate_context_binding(verification).may_access_personal_memory
    return False

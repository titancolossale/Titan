# =====================================
# Titan Provider Fallback Policy
# =====================================

"""Centralized provider fallback policy for Brain routing and runtime (P10B-901–P10B-906)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.settings import (
    TITAN_ALLOW_CROSS_PROVIDER,
    TITAN_ALLOW_PROVIDER_FALLBACK,
    TITAN_ALLOW_RETRY,
    TITAN_FALLBACK_TIMEOUT,
)
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState

_BLOCKED_HEALTH = frozenset({
    ToolHealthState.OFFLINE,
    ToolHealthState.DISABLED,
    ToolHealthState.MISCONFIGURED,
    ToolHealthState.MISSING_CREDENTIALS,
})

_RETRYABLE_HEALTH = frozenset({
    ToolHealthState.DEGRADED,
    ToolHealthState.UNKNOWN,
})


class FallbackDecision(str, Enum):
    """Supported fallback routing decisions (P10B-902)."""

    ALLOW_FALLBACK = "allow_fallback"
    DENY_FALLBACK = "deny_fallback"
    RETRY_ORIGINAL = "retry_original"
    REQUEST_CONFIRMATION = "request_confirmation"
    ABORT = "abort"


@dataclass(frozen=True)
class ProviderFallbackPolicyConfig:
    """Runtime configuration for provider fallback evaluation (P10B-906)."""

    allow_provider_fallback: bool = TITAN_ALLOW_PROVIDER_FALLBACK
    allow_cross_provider: bool = TITAN_ALLOW_CROSS_PROVIDER
    allow_retry: bool = TITAN_ALLOW_RETRY
    fallback_timeout: float = TITAN_FALLBACK_TIMEOUT

    @property
    def policy_name(self) -> str:
        """Compact policy label for DecisionReport serialization."""
        flags = []
        if self.allow_provider_fallback:
            flags.append("fallback")
        if self.allow_cross_provider:
            flags.append("cross_provider")
        if self.allow_retry:
            flags.append("retry")
        return "+".join(flags) if flags else "strict"


@dataclass(frozen=True)
class FallbackEvaluationContext:
    """Inputs for centralized fallback policy evaluation (P10B-901)."""

    provider_id: str
    capability: str
    execution_mode: ExecutionMode
    provider_health: ToolHealthState
    confirmation_required: bool = False
    user_confirmed: bool = False
    failure_reason: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True)
class FallbackPolicyOutcome:
    """Result of policy evaluation."""

    decision: FallbackDecision
    reason: str
    policy: str


class ProviderFallbackPolicy:
    """Evaluate whether provider fallback is allowed, required, or forbidden."""

    def __init__(
        self,
        config: ProviderFallbackPolicyConfig | None = None,
        *,
        performance_model: ProviderPerformanceModel | None = None,
    ) -> None:
        self.config = config or ProviderFallbackPolicyConfig()
        self.performance_model = performance_model

    def evaluate(self, context: FallbackEvaluationContext) -> FallbackPolicyOutcome:
        """Evaluate fallback policy from health, mode, capability, and user state."""
        policy_label = self.config.policy_name

        if context.provider_health == ToolHealthState.ONLINE:
            if self.config.allow_provider_fallback:
                return FallbackPolicyOutcome(
                    decision=FallbackDecision.ALLOW_FALLBACK,
                    reason="Provider healthy; fallback permitted if execution fails.",
                    policy=policy_label,
                )
            return FallbackPolicyOutcome(
                decision=FallbackDecision.DENY_FALLBACK,
                reason="Provider healthy; fallback disabled by configuration.",
                policy=policy_label,
            )

        if context.provider_health in _RETRYABLE_HEALTH and self.config.allow_retry:
            if self._should_prefer_fallback_from_history(context):
                return self._historical_fallback_outcome(context, policy_label)
            return FallbackPolicyOutcome(
                decision=FallbackDecision.RETRY_ORIGINAL,
                reason=(
                    f"Provider {context.provider_id!r} degraded "
                    f"({context.provider_health.value}); retry original before fallback."
                ),
                policy=policy_label,
            )

        if context.provider_health in _BLOCKED_HEALTH:
            return self._evaluate_blocked_provider(context, policy_label)

        if context.failure_reason and self.config.allow_retry:
            if self._should_prefer_fallback_from_history(context):
                return self._historical_fallback_outcome(context, policy_label)
            return FallbackPolicyOutcome(
                decision=FallbackDecision.RETRY_ORIGINAL,
                reason=f"Transient failure: {context.failure_reason}; retry original provider.",
                policy=policy_label,
            )

        return self._evaluate_blocked_provider(context, policy_label)

    def _evaluate_blocked_provider(
        self,
        context: FallbackEvaluationContext,
        policy_label: str,
    ) -> FallbackPolicyOutcome:
        if not self.config.allow_provider_fallback:
            if not self.config.allow_retry:
                return FallbackPolicyOutcome(
                    decision=FallbackDecision.ABORT,
                    reason=(
                        f"Provider {context.provider_id!r} unavailable; "
                        "retry and fallback both disabled."
                    ),
                    policy=policy_label,
                )
            return FallbackPolicyOutcome(
                decision=FallbackDecision.DENY_FALLBACK,
                reason=(
                    f"Provider {context.provider_id!r} unavailable "
                    f"({context.provider_health.value}); fallback disabled by policy."
                ),
                policy=policy_label,
            )

        if not self.config.allow_cross_provider:
            return FallbackPolicyOutcome(
                decision=FallbackDecision.DENY_FALLBACK,
                reason=(
                    f"Provider {context.provider_id!r} unavailable; "
                    "cross-provider fallback disabled by policy."
                ),
                policy=policy_label,
            )

        if self._requires_confirmation(context):
            return FallbackPolicyOutcome(
                decision=FallbackDecision.REQUEST_CONFIRMATION,
                reason=(
                    f"Cross-provider fallback from {context.provider_id!r} "
                    f"requires user confirmation in {context.execution_mode.value} mode."
                ),
                policy=policy_label,
            )

        return FallbackPolicyOutcome(
            decision=FallbackDecision.ALLOW_FALLBACK,
            reason=(
                f"Provider {context.provider_id!r} unavailable "
                f"({context.provider_health.value}); cross-provider fallback allowed."
            ),
            policy=policy_label,
        )

    @staticmethod
    def _requires_confirmation(context: FallbackEvaluationContext) -> bool:
        if context.user_confirmed:
            return False
        if context.execution_mode != ExecutionMode.LIVE:
            return False
        if context.confirmation_required:
            return True
        return context.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}

    @staticmethod
    def allows_fallback(decision: FallbackDecision) -> bool:
        """Return True when runtime may switch providers."""
        return decision == FallbackDecision.ALLOW_FALLBACK

    def _should_prefer_fallback_from_history(
        self,
        context: FallbackEvaluationContext,
    ) -> bool:
        """Use telemetry performance to prefer fallback over retry (P10B-1203)."""
        if self.performance_model is None or not self.config.allow_provider_fallback:
            return False
        return self.performance_model.is_historically_degraded(context.provider_id)

    def _historical_fallback_outcome(
        self,
        context: FallbackEvaluationContext,
        policy_label: str,
    ) -> FallbackPolicyOutcome:
        metrics = self.performance_model.get_metrics(context.provider_id)
        if not self.config.allow_cross_provider:
            return FallbackPolicyOutcome(
                decision=FallbackDecision.DENY_FALLBACK,
                reason=(
                    f"Provider {context.provider_id!r} historically degraded "
                    f"(score={metrics.performance_score:.0f}); "
                    "cross-provider fallback disabled by policy."
                ),
                policy=policy_label,
            )
        if self._requires_confirmation(context):
            return FallbackPolicyOutcome(
                decision=FallbackDecision.REQUEST_CONFIRMATION,
                reason=(
                    f"Provider {context.provider_id!r} historically degraded "
                    f"(score={metrics.performance_score:.0f}); "
                    "cross-provider fallback requires confirmation."
                ),
                policy=policy_label,
            )
        return FallbackPolicyOutcome(
            decision=FallbackDecision.ALLOW_FALLBACK,
            reason=(
                f"Provider {context.provider_id!r} historically degraded "
                f"(score={metrics.performance_score:.0f}, "
                f"confidence={metrics.historical_confidence:.2f}); "
                "telemetry prefers cross-provider fallback."
            ),
            policy=policy_label,
        )

    @staticmethod
    def parse_health(value: str | ToolHealthState | None) -> ToolHealthState:
        """Parse health state from report or metadata strings."""
        if isinstance(value, ToolHealthState):
            return value
        if not value:
            return ToolHealthState.UNKNOWN
        try:
            return ToolHealthState(str(value).lower())
        except ValueError:
            return ToolHealthState.UNKNOWN


def format_fallback_user_notice(
    outcome: object,
    *,
    fallback_decision: str = "",
) -> str:
    """Surface fallback outcomes clearly to the user (P10B-905)."""
    fallback_used = bool(getattr(outcome, "fallback_used", False))
    replacement_provider = getattr(outcome, "replacement_provider", None)
    if fallback_used and replacement_provider:
        original = (
            getattr(outcome, "original_provider", None)
            or getattr(outcome, "planned_provider", None)
            or "inconnu"
        )
        display = _provider_display_name(str(replacement_provider))
        return (
            f"Provider d'origine {original} indisponible. "
            f"Repli exécuté via {display}."
        )

    provider_unavailable = bool(getattr(outcome, "provider_unavailable", False))
    if provider_unavailable and not fallback_used:
        if fallback_decision == FallbackDecision.DENY_FALLBACK.value:
            original = (
                getattr(outcome, "original_provider", None)
                or getattr(outcome, "provider_id", None)
                or "inconnu"
            )
            return (
                f"Provider d'origine {original} indisponible. "
                "Repli refusé par la politique."
            )
        if fallback_decision == FallbackDecision.REQUEST_CONFIRMATION.value:
            return (
                "Repli provider nécessite une confirmation utilisateur "
                "avant exécution."
            )
        if fallback_decision == FallbackDecision.ABORT.value:
            return "Exécution provider interrompue par la politique de repli."

    return ""


def _provider_display_name(provider_id: str) -> str:
    """Map internal provider ids to user-friendly labels."""
    labels = {
        "web_search": "WebSearchProvider",
        "web_search_fallback": "FallbackWebSearchProvider",
        "brave_search": "BraveSearchProvider",
        "file_system": "FileSystemProvider",
        "github": "GitHubProvider",
        "calendar": "CalendarProvider",
    }
    return labels.get(provider_id, provider_id)

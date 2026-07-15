# =====================================
# Titan Tool Decision Engine
# =====================================

"""Orchestrate intent classification, tool need detection, ranking, and fallback (P10B-006)."""

from __future__ import annotations

from config.settings import TITAN_TOOL_DEFAULT_EXECUTION_MODE
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.intent import Intent
from tools.decision.intent_classifier import IntentClassifier
from tools.decision.models import (
    DEFAULT_AVAILABLE_TOOLS,
    CandidateProvider,
    CandidateTool,
    FallbackAction,
    ToolDecisionReport,
)
from tools.decision.provider_ranker import ProviderRanker, _TOOL_CAPABILITY
from tools.decision.tool_need_detector import ToolNeedDetector
from tools.decision.tool_ranker import ToolRanker
from tools.providers.provider_fallback_policy import (
    FallbackEvaluationContext,
    ProviderFallbackPolicy,
)
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.tool_enums import ExecutionMode, RiskLevel

_TOOL_RISK: dict[str, RiskLevel] = {
    "time": RiskLevel.SAFE,
    "file_read": RiskLevel.LOW,
    "file_write": RiskLevel.HIGH,
    "python_exec": RiskLevel.HIGH,
    "web_search": RiskLevel.LOW,
    "calendar": RiskLevel.LOW,
    "email": RiskLevel.LOW,
    "trading": RiskLevel.MEDIUM,
    "github": RiskLevel.LOW,
    "obsidian": RiskLevel.LOW,
    "browser": RiskLevel.LOW,
}

_CONFIRMATION_TOOLS: frozenset[str] = frozenset({"file_write", "python_exec"})

_MIN_SELECTION_SCORE = 40.0
_MIN_PROVIDER_SCORE = 45.0
_MIN_PROVIDER_CONFIDENCE = 0.55
_PROVIDER_AMBIGUITY_MARGIN = 12.0


def _parse_execution_mode(value: str) -> ExecutionMode:
    try:
        return ExecutionMode(value.lower())
    except ValueError:
        return ExecutionMode.LIVE


class ToolDecisionEngine:
    """Independent decision layer between user intent and tool execution."""

    def __init__(
        self,
        *,
        classifier: IntentClassifier | None = None,
        need_detector: ToolNeedDetector | None = None,
        ranker: ToolRanker | None = None,
        provider_ranker: ProviderRanker | None = None,
        fallback_policy: ProviderFallbackPolicy | None = None,
        performance_model: ProviderPerformanceModel | None = None,
    ) -> None:
        self.classifier = classifier or IntentClassifier()
        self.need_detector = need_detector or ToolNeedDetector()
        self.ranker = ranker or ToolRanker()
        self.performance_model = performance_model
        self.provider_ranker = provider_ranker or ProviderRanker(
            performance_model=performance_model,
        )
        self.fallback_policy = fallback_policy or ProviderFallbackPolicy(
            performance_model=performance_model,
        )

    def decide(
        self,
        message: str,
        *,
        available_tools: frozenset[str] | None = None,
        availability_resolver: CapabilityAvailabilityResolver | None = None,
    ) -> ToolDecisionReport:
        """Produce the canonical tool decision report for a user message."""
        if available_tools is None and availability_resolver is not None:
            tools = availability_resolver.resolve_available_tools()
        else:
            tools = available_tools or DEFAULT_AVAILABLE_TOOLS
        classification = self.classifier.classify(message)
        need = self.need_detector.assess(message, classification)
        candidates = self.ranker.rank(
            message,
            classification,
            available_tools=tools,
        )
        if availability_resolver is not None:
            candidates = availability_resolver.adjust_candidates(candidates)

        if not need.tool_required:
            return self._direct_answer_report(classification, candidates, need.reason)

        valid_candidates = tuple(c for c in candidates if c.tool_name in tools)
        if not valid_candidates:
            return self._no_capability_report(classification, need.reason)

        selected = valid_candidates[0]
        if selected.score < _MIN_SELECTION_SCORE:
            return self._no_capability_report(
                classification,
                f"Top candidate score {selected.score} below threshold {_MIN_SELECTION_SCORE}",
            )

        risk, confirmation = self._resolve_risk_and_confirmation(
            selected.tool_name,
            availability_resolver=availability_resolver,
        )

        provider_outcome = self._resolve_provider(
            message,
            classification,
            selected_tool=selected.tool_name,
            availability_resolver=availability_resolver,
        )
        if provider_outcome is not None:
            if provider_outcome.fallback_action == FallbackAction.CLARIFICATION:
                return provider_outcome
            if provider_outcome.fallback_action == FallbackAction.NO_CAPABILITY:
                return provider_outcome

        reasoning_summary = (
            f"Intent={classification.intent.value} (confidence={classification.confidence:.2f}); "
            f"tool={selected.tool_name} (score={selected.score:.0f}); "
        )
        if provider_outcome and provider_outcome.selected_provider:
            reasoning_summary += (
                f"provider={provider_outcome.selected_provider} "
                f"(ranking_score={provider_outcome.ranking_score:.0f})"
            )
        else:
            reasoning_summary += f"reason={selected.reason}"

        decision_reason = (
            f"Selected {selected.tool_name} (score={selected.score:.0f}): {selected.reason}"
        )
        if provider_outcome and provider_outcome.selected_provider:
            decision_reason += (
                f"; provider {provider_outcome.selected_provider} "
                f"(ranking_score={provider_outcome.ranking_score:.0f})"
            )

        return self._apply_fallback_policy(
            self._enrich_performance(
                ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=True,
            candidate_tools=valid_candidates,
            selected_tool=selected.tool_name,
            decision_reason=decision_reason,
            risk_level=risk,
            confirmation_required=confirmation,
            fallback_action=FallbackAction.EXECUTE_TOOL,
            classification_reason=classification.reason,
            selected_provider=(
                provider_outcome.selected_provider if provider_outcome else None
            ),
            planned_provider=(
                provider_outcome.selected_provider if provider_outcome else None
            ),
            provider_score=(
                provider_outcome.ranking_score if provider_outcome else None
            ),
            provider_health=(
                provider_outcome.candidate_providers[0].health_state
                if provider_outcome and provider_outcome.candidate_providers
                else None
            ),
            candidate_providers=(
                provider_outcome.candidate_providers if provider_outcome else ()
            ),
            ranking_score=(
                provider_outcome.ranking_score if provider_outcome else None
            ),
            reasoning_summary=reasoning_summary,
            execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
                ),
                provider_outcome.selected_provider if provider_outcome else None,
            ),
            selected_tool=selected.tool_name,
            risk_level=risk,
            confirmation_required=confirmation,
        )

    def _resolve_provider(
        self,
        message: str,
        classification,
        *,
        selected_tool: str,
        availability_resolver: CapabilityAvailabilityResolver | None,
    ) -> ToolDecisionReport | None:
        """Rank providers for provider-backed tools; return fallback report when blocked."""
        if selected_tool not in _TOOL_CAPABILITY:
            return None

        registry = (
            availability_resolver.provider_registry
            if availability_resolver is not None
            else None
        )
        health_monitor = (
            availability_resolver.health_monitor
            if availability_resolver is not None
            else None
        )
        configuration_store = (
            registry.configuration_store if registry is not None else None
        )
        execution_mode = _parse_execution_mode(TITAN_TOOL_DEFAULT_EXECUTION_MODE)

        provider_candidates = self.provider_ranker.rank(
            message,
            classification,
            selected_tool=selected_tool,
            provider_registry=registry,
            health_monitor=health_monitor,
            execution_mode=execution_mode,
            configuration_store=configuration_store,
        )

        if not provider_candidates:
            return self._no_capability_report(
                classification,
                f"No provider available for tool {selected_tool}",
            )

        top = provider_candidates[0]
        if top.score < _MIN_PROVIDER_SCORE:
            return self._clarification_report(
                classification,
                selected_tool=selected_tool,
                provider_candidates=provider_candidates,
                reason=(
                    f"Provider confidence too low (top score {top.score} "
                    f"< {_MIN_PROVIDER_SCORE})"
                ),
            )

        if len(provider_candidates) > 1:
            margin = top.score - provider_candidates[1].score
            if (
                margin < _PROVIDER_AMBIGUITY_MARGIN
                and classification.confidence < _MIN_PROVIDER_CONFIDENCE
            ):
                return self._clarification_report(
                    classification,
                    selected_tool=selected_tool,
                    provider_candidates=provider_candidates,
                    reason=(
                        f"Ambiguous provider routing (margin={margin:.1f}, "
                        f"confidence={classification.confidence:.2f})"
                    ),
                )

        return self._apply_fallback_policy(
            self._enrich_performance(
                ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=True,
            candidate_tools=(),
            selected_tool=selected_tool,
            decision_reason="",
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.EXECUTE_TOOL,
            classification_reason=classification.reason,
            selected_provider=top.provider_id,
            planned_provider=top.provider_id,
            provider_score=top.score,
            provider_health=top.health_state,
            candidate_providers=provider_candidates,
            ranking_score=top.score,
            reasoning_summary=(
                f"Provider {top.provider_id} selected (score={top.score:.0f}): {top.reason}"
            ),
            execution_mode=TITAN_TOOL_DEFAULT_EXECUTION_MODE,
                ),
                top.provider_id,
            ),
            selected_tool=selected_tool,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
        )

    def _resolve_risk_and_confirmation(
        self,
        tool_name: str,
        *,
        availability_resolver: CapabilityAvailabilityResolver | None,
    ) -> tuple[RiskLevel, bool]:
        """Resolve risk and confirmation from live catalog when available."""
        if availability_resolver is not None:
            risk = availability_resolver.resolve_risk_level(tool_name, fallback=RiskLevel.MEDIUM)
            confirmation = availability_resolver.requires_confirmation(tool_name)
            return risk, confirmation
        risk = _TOOL_RISK.get(tool_name, RiskLevel.MEDIUM)
        confirmation = tool_name in _CONFIRMATION_TOOLS
        return risk, confirmation

    def _direct_answer_report(
        self,
        classification,
        candidates: tuple[CandidateTool, ...],
        reason: str,
    ) -> ToolDecisionReport:
        return ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=False,
            candidate_tools=candidates,
            selected_tool=None,
            decision_reason=reason,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.DIRECT_ANSWER,
            classification_reason=classification.reason,
            reasoning_summary=reason,
        )

    def _clarification_report(
        self,
        classification,
        *,
        selected_tool: str | None = None,
        provider_candidates: tuple[CandidateProvider, ...] = (),
        reason: str,
    ) -> ToolDecisionReport:
        """Return clarification request instead of executing the wrong provider (P10B-705)."""
        candidate_summary = ", ".join(
            f"{item.provider_id}({item.score:.0f})" for item in provider_candidates[:3]
        )
        summary = (
            f"{reason}. Candidates: {candidate_summary or 'none'}. "
            "Clarification required before provider execution."
        )
        return ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=True,
            candidate_tools=(),
            selected_tool=selected_tool,
            decision_reason=summary,
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.CLARIFICATION,
            classification_reason=classification.reason,
            candidate_providers=provider_candidates,
            ranking_score=(
                provider_candidates[0].score if provider_candidates else None
            ),
            reasoning_summary=summary,
        )

    def _no_capability_report(
        self,
        classification,
        reason: str,
    ) -> ToolDecisionReport:
        intent_label = classification.intent.value
        if classification.intent in {Intent.EMAIL, Intent.TRADING}:
            detail = (
                f"Intent {intent_label} requires a capability not yet available "
                f"in the registered tool set"
            )
        else:
            detail = f"No registered tool satisfies intent {intent_label}"

        return ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=True,
            candidate_tools=(),
            selected_tool=None,
            decision_reason=f"{reason}. {detail}",
            risk_level=RiskLevel.SAFE,
            confirmation_required=False,
            fallback_action=FallbackAction.NO_CAPABILITY,
            classification_reason=classification.reason,
            reasoning_summary=f"{reason}. {detail}",
        )

    def _apply_fallback_policy(
        self,
        report: ToolDecisionReport,
        *,
        selected_tool: str,
        risk_level: RiskLevel,
        confirmation_required: bool,
        user_confirmed: bool = False,
    ) -> ToolDecisionReport:
        """Evaluate centralized fallback policy and enrich DecisionReport (P10B-903)."""
        if selected_tool not in _TOOL_CAPABILITY or not report.selected_provider:
            return report

        capability = _TOOL_CAPABILITY[selected_tool]
        execution_mode = _parse_execution_mode(
            report.execution_mode or TITAN_TOOL_DEFAULT_EXECUTION_MODE,
        )
        health = ProviderFallbackPolicy.parse_health(report.provider_health)

        outcome = self.fallback_policy.evaluate(
            FallbackEvaluationContext(
                provider_id=report.selected_provider,
                capability=capability,
                execution_mode=execution_mode,
                provider_health=health,
                confirmation_required=confirmation_required,
                user_confirmed=user_confirmed,
                risk_level=risk_level,
            ),
        )
        return report.with_fallback_policy(
            fallback_policy=outcome.policy,
            fallback_decision=outcome.decision.value,
            fallback_reason=outcome.reason,
        )

    def _enrich_performance(
        self,
        report: ToolDecisionReport,
        provider_id: str | None,
    ) -> ToolDecisionReport:
        """Attach telemetry performance metadata when a performance model is wired."""
        if self.performance_model is None or not provider_id:
            return report
        metrics = self.performance_model.get_metrics(provider_id)
        return report.with_performance_metrics(
            performance_score=metrics.performance_score,
            ranking_reason=metrics.ranking_reason,
            historical_confidence=metrics.historical_confidence,
        )

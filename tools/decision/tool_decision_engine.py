# =====================================
# Titan Tool Decision Engine
# =====================================

"""Orchestrate intent classification, tool need detection, ranking, and fallback (P10B-006)."""

from __future__ import annotations

from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.intent import Intent
from tools.decision.intent_classifier import IntentClassifier
from tools.decision.models import (
    DEFAULT_AVAILABLE_TOOLS,
    CandidateTool,
    FallbackAction,
    ToolDecisionReport,
)
from tools.decision.tool_need_detector import ToolNeedDetector
from tools.decision.tool_ranker import ToolRanker
from tools.tool_enums import RiskLevel

_TOOL_RISK: dict[str, RiskLevel] = {
    "time": RiskLevel.SAFE,
    "file_read": RiskLevel.LOW,
    "file_write": RiskLevel.MEDIUM,
    "python_exec": RiskLevel.HIGH,
    "web_search": RiskLevel.LOW,
    "calendar": RiskLevel.LOW,
}

_CONFIRMATION_TOOLS: frozenset[str] = frozenset({"file_write", "python_exec"})

_MIN_SELECTION_SCORE = 40.0


class ToolDecisionEngine:
    """Independent decision layer between user intent and tool execution."""

    def __init__(
        self,
        *,
        classifier: IntentClassifier | None = None,
        need_detector: ToolNeedDetector | None = None,
        ranker: ToolRanker | None = None,
    ) -> None:
        self.classifier = classifier or IntentClassifier()
        self.need_detector = need_detector or ToolNeedDetector()
        self.ranker = ranker or ToolRanker()

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

        return ToolDecisionReport(
            intent=classification.intent,
            confidence=classification.confidence,
            tool_required=True,
            candidate_tools=valid_candidates,
            selected_tool=selected.tool_name,
            decision_reason=(
                f"Selected {selected.tool_name} (score={selected.score:.0f}): "
                f"{selected.reason}"
            ),
            risk_level=risk,
            confirmation_required=confirmation,
            fallback_action=FallbackAction.EXECUTE_TOOL,
            classification_reason=classification.reason,
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
        )

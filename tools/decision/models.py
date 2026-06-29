# =====================================
# Titan Tool Decision — Models
# =====================================

"""Structured decision artifacts for the Tool Decision Engine (Phase 10B — P10B-005)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tools.decision.intent import Intent
from tools.tool_enums import RiskLevel


class FallbackAction(str, Enum):
    """Outcome when no tool execution should proceed."""

    DIRECT_ANSWER = "direct_answer"
    NO_CAPABILITY = "no_capability"
    EXECUTE_TOOL = "execute_tool"


@dataclass(frozen=True)
class IntentClassification:
    """Result of intent classification (P10B-001, P10B-002)."""

    intent: Intent
    confidence: float
    reason: str


@dataclass(frozen=True)
class CandidateTool:
    """Ranked tool candidate with relevance score (P10B-004)."""

    tool_name: str
    score: float
    reason: str = ""


@dataclass(frozen=True)
class ToolDecisionReport:
    """Canonical internal decision output for tool selection (P10B-005)."""

    intent: Intent
    confidence: float
    tool_required: bool
    candidate_tools: tuple[CandidateTool, ...]
    selected_tool: str | None
    decision_reason: str
    risk_level: RiskLevel
    confirmation_required: bool
    fallback_action: FallbackAction = FallbackAction.DIRECT_ANSWER
    classification_reason: str = ""

    @property
    def intent_reason(self) -> str:
        """Alias for classification reason (backward-compatible accessor)."""
        return self.classification_reason

    def to_dict(self) -> dict:
        """Serialize for logging, tests, and future pipeline stages."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "tool_required": self.tool_required,
            "candidate_tools": [
                {"tool_name": c.tool_name, "score": c.score, "reason": c.reason}
                for c in self.candidate_tools
            ],
            "selected_tool": self.selected_tool,
            "decision_reason": self.decision_reason,
            "risk_level": self.risk_level.value,
            "confirmation_required": self.confirmation_required,
            "fallback_action": self.fallback_action.value,
            "classification_reason": self.classification_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolDecisionReport:
        """Deserialize a report stored in execution context metadata."""
        return cls(
            intent=Intent(data["intent"]),
            confidence=float(data["confidence"]),
            tool_required=bool(data["tool_required"]),
            candidate_tools=tuple(
                CandidateTool(
                    tool_name=item["tool_name"],
                    score=float(item["score"]),
                    reason=item.get("reason", ""),
                )
                for item in data.get("candidate_tools", [])
            ),
            selected_tool=data.get("selected_tool"),
            decision_reason=str(data.get("decision_reason", "")),
            risk_level=RiskLevel(data.get("risk_level", RiskLevel.SAFE.value)),
            confirmation_required=bool(data.get("confirmation_required", False)),
            fallback_action=FallbackAction(
                data.get("fallback_action", FallbackAction.DIRECT_ANSWER.value),
            ),
            classification_reason=str(data.get("classification_reason", "")),
        )


@dataclass
class ToolNeedAssessment:
    """Output of the tool-needed detector (P10B-003)."""

    tool_required: bool
    reason: str


@dataclass
class IntentRule:
    """Keyword rule contributing to intent classification."""

    intent: Intent
    keywords: tuple[str, ...]
    weight: float
    reason: str

    def score(self, lowered: str) -> float:
        """Return weighted score when any keyword matches."""
        if not self.keywords:
            return 0.0
        hits = sum(1 for kw in self.keywords if kw in lowered)
        if hits == 0:
            return 0.0
        return self.weight * min(1.0 + (hits - 1) * 0.1, 1.5)


DEFAULT_AVAILABLE_TOOLS: frozenset[str] = frozenset(
    {
        "time",
        "file_read",
        "file_write",
        "python_exec",
        "web_search",
        "calendar",
    },
)

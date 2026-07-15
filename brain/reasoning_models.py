# =====================================
# Titan Reasoning Engine Models
# =====================================

"""Structured models for the multi-step Reasoning Engine V1.

All models are serializable via ``to_dict()`` for web UI and future APIs.
The Reasoning Engine produces these artifacts only — it never executes tools.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReasoningStage(str, Enum):
    """Canonical stages of the reasoning pipeline."""

    UNDERSTAND = "understand"
    CONTEXT = "context"
    DECOMPOSE = "decompose"
    ALTERNATIVES = "alternatives"
    EVALUATE = "evaluate"
    RECOMMEND = "recommend"


class ReasoningDomain(str, Enum):
    """High-level domain classification for a request."""

    GENERAL = "general"
    SOFTWARE = "software"
    ARCHITECTURE = "architecture"
    CODE = "code"
    PLANNING = "planning"
    TRADING = "trading"
    AUTOMATION = "automation"
    RESEARCH = "research"
    MISSION = "mission"
    WORKSPACE = "workspace"


class ReasoningUrgency(str, Enum):
    """Detected urgency level."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


def new_reasoning_id(prefix: str = "reason") -> str:
    """Generate a stable unique id for reasoning artifacts."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class RequestUnderstanding:
    """Stage 1 output — parsed request semantics."""

    objective: str
    constraints: tuple[str, ...]
    urgency: ReasoningUrgency
    domain: ReasoningDomain
    requested_output: str
    raw_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "constraints": list(self.constraints),
            "urgency": self.urgency.value,
            "domain": self.domain.value,
            "requested_output": self.requested_output,
            "raw_message": self.raw_message,
        }


@dataclass(frozen=True)
class ReasoningStep:
    """One logical reasoning unit from problem decomposition."""

    id: str
    title: str
    description: str
    stage: ReasoningStage
    order: int
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "stage": self.stage.value,
            "order": self.order,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class ReasoningRisk:
    """Identified risk with severity and mitigation hint."""

    id: str
    summary: str
    severity: str
    mitigation: str
    source: str = "reasoning_engine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "severity": self.severity,
            "mitigation": self.mitigation,
            "source": self.source,
        }


@dataclass(frozen=True)
class ReasoningAssumption:
    """Explicit assumption made during reasoning."""

    id: str
    statement: str
    confidence: float
    validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "confidence": round(self.confidence, 3),
            "validated": self.validated,
        }


@dataclass(frozen=True)
class ReasoningQuestion:
    """Open question or missing information detected."""

    id: str
    question: str
    importance: float
    category: str = "missing_information"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "importance": round(self.importance, 3),
            "category": self.category,
        }


@dataclass(frozen=True)
class ReasoningAlternative:
    """One candidate strategy with tradeoff metadata."""

    id: str
    description: str
    advantages: tuple[str, ...]
    disadvantages: tuple[str, ...]
    estimated_complexity: str
    estimated_risk: str
    confidence: float
    rank: int = 0
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "advantages": list(self.advantages),
            "disadvantages": list(self.disadvantages),
            "estimated_complexity": self.estimated_complexity,
            "estimated_risk": self.estimated_risk,
            "confidence": round(self.confidence, 3),
            "rank": self.rank,
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
        }


@dataclass(frozen=True)
class ReasoningRecommendation:
    """Final recommended strategy from stage 6."""

    strategy: str
    supporting_arguments: tuple[str, ...]
    confidence: float
    selected_alternative_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "supporting_arguments": list(self.supporting_arguments),
            "confidence": round(self.confidence, 3),
            "selected_alternative_id": self.selected_alternative_id,
        }


@dataclass(frozen=True)
class ReasoningSummary:
    """Aggregate scores and headline understanding."""

    objective: str
    domain: ReasoningDomain
    urgency: ReasoningUrgency
    requested_output: str
    constraints: tuple[str, ...]
    confidence_score: float
    reasoning_quality_score: float
    completeness_score: float
    clarification_required: bool
    headline: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "domain": self.domain.value,
            "urgency": self.urgency.value,
            "requested_output": self.requested_output,
            "constraints": list(self.constraints),
            "confidence_score": round(self.confidence_score, 3),
            "reasoning_quality_score": round(self.reasoning_quality_score, 3),
            "completeness_score": round(self.completeness_score, 3),
            "clarification_required": self.clarification_required,
            "headline": self.headline,
        }


@dataclass(frozen=True)
class ReasoningResult:
    """Complete output of one reasoning cycle."""

    message: str
    understanding: RequestUnderstanding
    summary: ReasoningSummary
    steps: tuple[ReasoningStep, ...]
    alternatives: tuple[ReasoningAlternative, ...]
    risks: tuple[ReasoningRisk, ...]
    assumptions: tuple[ReasoningAssumption, ...]
    open_questions: tuple[ReasoningQuestion, ...]
    recommendation: ReasoningRecommendation
    recommended_tools: tuple[str, ...] = ()
    context_sources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "understanding": self.understanding.to_dict(),
            "summary": self.summary.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "alternatives": [a.to_dict() for a in self.alternatives],
            "risks": [r.to_dict() for r in self.risks],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "recommendation": self.recommendation.to_dict(),
            "recommended_tools": list(self.recommended_tools),
            "context_sources": dict(self.context_sources),
        }

    def format_for_prompt(self) -> str:
        """Compact text block for LLM prompt injection."""
        lines = [
            "RAISONNEMENT STRUCTURÉ",
            f"Objectif: {self.summary.objective}",
            f"Domaine: {self.summary.domain.value}",
            f"Urgence: {self.summary.urgency.value}",
            f"Confiance: {self.summary.confidence_score:.2f}",
            f"Stratégie recommandée: {self.recommendation.strategy}",
        ]
        if self.recommendation.supporting_arguments:
            lines.append("Arguments:")
            lines.extend(f"  - {arg}" for arg in self.recommendation.supporting_arguments[:5])
        if self.open_questions:
            lines.append("Questions ouvertes:")
            lines.extend(f"  - {q.question}" for q in self.open_questions[:5])
        if self.risks:
            lines.append("Risques:")
            lines.extend(f"  - [{r.severity}] {r.summary}" for r in self.risks[:5])
        return "\n".join(lines)

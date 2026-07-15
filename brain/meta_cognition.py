# =====================================
# Titan Meta-Cognition Engine
# =====================================

"""Meta-Cognition Engine V1 — self-evaluation of reasoning and responses.

Evaluates confidence, completeness, uncertainty, ambiguity, missing
information, unsupported assumptions, conflicting evidence, and hallucination
risk before a response is finalized. Never generates answers and never
mutates reasoning, memory, knowledge, or missions.

V1 is evaluation-only — future versions may influence behavior.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain.cognitive_context_builder import CognitiveContext
    from brain.cognitive_context_builder import CognitiveContextBuilder
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.knowledge_learning_engine import KnowledgeLearningEngine
    from brain.reasoning_engine import ReasoningEngine
    from brain.reasoning_models import ReasoningResult
    from brain.world_model import WorldModel, WorldModelSnapshot
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_HEDGE_RE = re.compile(
    r"\b(maybe|perhaps|possibly|might|could be|not sure|uncertain|"
    r"peut[- ]?être|probablement|je pense que|il se peut)\b",
    re.IGNORECASE,
)
_ABSOLUTE_CLAIM_RE = re.compile(
    r"\b(always|never|definitely|certainly|guaranteed|100%|"
    r"toujours|jamais|sûrement|certainement|garanti)\b",
    re.IGNORECASE,
)
_SPECIFIC_FACT_RE = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d+(?:\.\d+)?%\b|\bversion\s+\d",
    re.IGNORECASE,
)
_VAGUE_RESPONSE_RE = re.compile(
    r"\b(it depends|ça dépend|hard to say|difficile à dire|"
    r"in general|en général|various factors)\b",
    re.IGNORECASE,
)


class HallucinationRisk(str, Enum):
    """Coarse hallucination risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningQuality(str, Enum):
    """Coarse reasoning quality classification."""

    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"


class RecommendationStrength(str, Enum):
    """How strongly meta-cognition supports proceeding."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


def new_meta_id(prefix: str = "meta") -> str:
    """Generate a stable unique id for meta-cognition artifacts."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class MetaCognitionRecommendation:
    """Advisory recommendation from meta-cognition — never auto-executed."""

    strength: RecommendationStrength
    summary: str
    factors: tuple[str, ...] = ()
    proceed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "strength": self.strength.value,
            "summary": self.summary,
            "factors": list(self.factors),
            "proceed": self.proceed,
        }


@dataclass(frozen=True)
class MetaCognitionReport:
    """Structured output of one meta-cognition evaluation cycle."""

    id: str
    evaluation_target: str
    confidence_score: float
    uncertainty_score: float
    ambiguity_score: float
    missing_information: tuple[str, ...]
    assumptions: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
    hallucination_risk: HallucinationRisk
    clarification_required: bool
    reasoning_quality: ReasoningQuality
    recommendation: MetaCognitionRecommendation
    message: str = ""
    sources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": SCHEMA_VERSION,
            "evaluation_target": self.evaluation_target,
            "confidence_score": round(self.confidence_score, 3),
            "uncertainty_score": round(self.uncertainty_score, 3),
            "ambiguity_score": round(self.ambiguity_score, 3),
            "missing_information": list(self.missing_information),
            "assumptions": list(self.assumptions),
            "conflicting_evidence": list(self.conflicting_evidence),
            "hallucination_risk": self.hallucination_risk.value,
            "clarification_required": self.clarification_required,
            "reasoning_quality": self.reasoning_quality.value,
            "recommendation": self.recommendation.to_dict(),
            "message": self.message,
            "sources": dict(self.sources),
        }

    def format_for_prompt(self) -> str:
        """Compact text block for optional LLM prompt injection."""
        lines = [
            "MÉTA-COGNITION",
            f"Cible: {self.evaluation_target}",
            f"Confiance: {self.confidence_score:.2f}",
            f"Incertitude: {self.uncertainty_score:.2f}",
            f"Ambiguïté: {self.ambiguity_score:.2f}",
            f"Qualité du raisonnement: {self.reasoning_quality.value}",
            f"Risque d'hallucination: {self.hallucination_risk.value}",
            f"Clarification requise: {'oui' if self.clarification_required else 'non'}",
            f"Recommandation: {self.recommendation.summary}",
        ]
        if self.missing_information:
            lines.append("Informations manquantes:")
            lines.extend(f"  - {item}" for item in self.missing_information[:5])
        if self.assumptions:
            lines.append("Hypothèses non validées:")
            lines.extend(f"  - {item}" for item in self.assumptions[:5])
        if self.conflicting_evidence:
            lines.append("Preuves contradictoires:")
            lines.extend(f"  - {item}" for item in self.conflicting_evidence[:5])
        return "\n".join(lines)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _quality_from_score(score: float) -> ReasoningQuality:
    if score >= 0.85:
        return ReasoningQuality.EXCELLENT
    if score >= 0.65:
        return ReasoningQuality.GOOD
    if score >= 0.45:
        return ReasoningQuality.FAIR
    return ReasoningQuality.POOR


def _risk_from_score(score: float) -> HallucinationRisk:
    if score >= 0.65:
        return HallucinationRisk.HIGH
    if score >= 0.35:
        return HallucinationRisk.MEDIUM
    return HallucinationRisk.LOW


def _strength_from_confidence(confidence: float) -> RecommendationStrength:
    if confidence >= 0.75:
        return RecommendationStrength.STRONG
    if confidence >= 0.5:
        return RecommendationStrength.MODERATE
    return RecommendationStrength.WEAK


class MetaCognitionEngine:
    """Evaluates Titan's own reasoning and responses — read-only, V1."""

    def __init__(
        self,
        *,
        reasoning_engine: ReasoningEngine | None = None,
        cognitive_context_builder: CognitiveContextBuilder | None = None,
        knowledge_learning_engine: KnowledgeLearningEngine | None = None,
        world_model: WorldModel | None = None,
        executive_function: ExecutiveFunction | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._context_builder = cognitive_context_builder
        self._knowledge_learning_engine = knowledge_learning_engine
        self._world_model = world_model
        self._executive_function = executive_function
        self._memory_service = memory_service
        self._last_report: MetaCognitionReport | None = None

    def evaluate_reasoning(
        self,
        reasoning: ReasoningResult,
        *,
        context: CognitiveContext | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
    ) -> MetaCognitionReport:
        """Evaluate structured reasoning output before response finalization."""
        missing: list[str] = [q.question for q in reasoning.open_questions]
        assumptions: list[str] = [
            a.statement for a in reasoning.assumptions if not a.validated
        ]
        conflicting: list[str] = self._detect_reasoning_conflicts(reasoning)

        base_confidence = reasoning.summary.confidence_score
        completeness = reasoning.summary.completeness_score
        quality_score = reasoning.summary.reasoning_quality_score

        uncertainty = self._uncertainty_from_reasoning(reasoning, assumptions)
        ambiguity = self._ambiguity_from_reasoning(reasoning)
        confidence = _clamp(
            base_confidence
            - (0.05 * len(missing))
            - (0.03 * len(assumptions))
            - (0.08 * len(conflicting)),
        )

        if context is not None:
            context_penalty = self._context_uncertainty_penalty(context)
            uncertainty = _clamp(uncertainty + context_penalty * 0.5)
            confidence = _clamp(confidence - context_penalty * 0.3)
            missing.extend(self._context_missing_items(context))

        if executive_evaluation is not None:
            if executive_evaluation.blocked_missions:
                uncertainty = _clamp(uncertainty + 0.1)
                conflicting.append(
                    "Executive Function reports blocked missions affecting focus",
                )

        hallucination_score = self._hallucination_score_reasoning(
            reasoning,
            context,
            assumptions,
        )
        clarification = (
            reasoning.summary.clarification_required
            or confidence < 0.55
            or len(missing) >= 2
            or hallucination_score >= 0.55
        )

        recommendation = self._build_recommendation(
            confidence=confidence,
            clarification_required=clarification,
            target="reasoning",
            factors=(
                f"Reasoning confidence: {base_confidence:.2f}",
                f"Completeness: {completeness:.2f}",
                f"Open questions: {len(missing)}",
            ),
        )

        report = MetaCognitionReport(
            id=new_meta_id(),
            evaluation_target="reasoning",
            confidence_score=confidence,
            uncertainty_score=uncertainty,
            ambiguity_score=ambiguity,
            missing_information=tuple(dict.fromkeys(missing)),
            assumptions=tuple(dict.fromkeys(assumptions)),
            conflicting_evidence=tuple(dict.fromkeys(conflicting)),
            hallucination_risk=_risk_from_score(hallucination_score),
            clarification_required=clarification,
            reasoning_quality=_quality_from_score(quality_score),
            recommendation=recommendation,
            message=reasoning.message,
            sources={
                "reasoning_domain": reasoning.summary.domain.value,
                "reasoning_urgency": reasoning.summary.urgency.value,
                "step_count": len(reasoning.steps),
                "alternative_count": len(reasoning.alternatives),
                "risk_count": len(reasoning.risks),
                "context_provided": context is not None,
                "executive_provided": executive_evaluation is not None,
            },
        )
        self._last_report = report
        return report

    def evaluate_context(
        self,
        context: CognitiveContext,
        *,
        world_snapshot: WorldModelSnapshot | None = None,
    ) -> MetaCognitionReport:
        """Evaluate assembled cognitive context sufficiency and coherence."""
        missing = self._context_missing_items(context)
        assumptions: list[str] = []
        conflicting: list[str] = []

        snapshot = world_snapshot or context.world_model
        if snapshot is not None:
            blockers = getattr(snapshot, "blockers", ()) or ()
            if blockers:
                conflicting.append(
                    f"World Model reports {len(blockers)} active blocker(s)",
                )
            opportunities = getattr(snapshot, "opportunities", ()) or ()
            if opportunities and blockers:
                conflicting.append(
                    "World Model shows both blockers and opportunities — priorities unclear",
                )

        if context.executive_priorities is not None:
            blocked = context.executive_priorities.blocked_missions
            if blocked:
                missing.append(
                    "Blocked missions may need resolution before proceeding",
                )

        memory_present = context.memories is not None and (
            context.memories.has_matches or bool(context.memories.text.strip())
        )
        knowledge_count = len(context.verified_knowledge or ())
        if not memory_present and knowledge_count == 0:
            assumptions.append("Proceeding without retrieved memory or verified knowledge")

        uncertainty = self._context_uncertainty_penalty(context)
        ambiguity = _clamp(
            0.2
            + (0.25 if not context.message.strip() else 0.0)
            + (0.15 if snapshot is None else 0.0)
            + (0.1 if not context.active_missions and "mission" in context.message.lower() else 0.0),
        )
        confidence = _clamp(
            1.0
            - uncertainty
            - (0.08 * len(missing))
            - (0.05 * len(assumptions)),
        )
        quality_score = _clamp(
            0.5
            + (0.15 if snapshot is not None else 0.0)
            + (0.1 if memory_present else 0.0)
            + (0.1 if knowledge_count > 0 else 0.0)
            + (0.1 if context.architecture is not None else 0.0),
        )
        hallucination_score = _clamp(
            0.15
            + (0.25 if not memory_present and not knowledge_count else 0.0)
            + (0.2 if snapshot is None else 0.0),
        )
        clarification = confidence < 0.55 or len(missing) >= 2

        recommendation = self._build_recommendation(
            confidence=confidence,
            clarification_required=clarification,
            target="context",
            factors=(
                f"Context build mode: {context.build_mode.value}",
                f"Verified knowledge items: {knowledge_count}",
                f"World model present: {snapshot is not None}",
            ),
        )

        report = MetaCognitionReport(
            id=new_meta_id(),
            evaluation_target="context",
            confidence_score=confidence,
            uncertainty_score=uncertainty,
            ambiguity_score=ambiguity,
            missing_information=tuple(dict.fromkeys(missing)),
            assumptions=tuple(dict.fromkeys(assumptions)),
            conflicting_evidence=tuple(dict.fromkeys(conflicting)),
            hallucination_risk=_risk_from_score(hallucination_score),
            clarification_required=clarification,
            reasoning_quality=_quality_from_score(quality_score),
            recommendation=recommendation,
            message=context.message,
            sources={
                "build_mode": context.build_mode.value,
                "user": context.user,
                "project_id": context.project_id,
                "memory_present": memory_present,
                "verified_knowledge_count": knowledge_count,
                "world_model_present": snapshot is not None,
                "active_mission_count": len(context.active_missions or ()),
            },
        )
        self._last_report = report
        return report

    def evaluate_response(
        self,
        response: str,
        *,
        reasoning: ReasoningResult | None = None,
        context: CognitiveContext | None = None,
        message: str = "",
    ) -> MetaCognitionReport:
        """Evaluate a candidate response before it is sent to the user."""
        missing: list[str] = []
        assumptions: list[str] = []
        conflicting: list[str] = []
        response_text = (response or "").strip()

        if not response_text:
            missing.append("Response is empty")
        if len(response_text) < 40 and len(message) > 80:
            missing.append("Response may be too brief for the complexity of the request")

        hedge_matches = len(_HEDGE_RE.findall(response_text))
        absolute_matches = len(_ABSOLUTE_CLAIM_RE.findall(response_text))
        specific_facts = len(_SPECIFIC_FACT_RE.findall(response_text))
        vague_matches = len(_VAGUE_RESPONSE_RE.findall(response_text))

        if hedge_matches >= 2:
            assumptions.append("Response relies on hedging language")
        if vague_matches >= 1:
            assumptions.append("Response uses vague generalizations")

        uncertainty = _clamp(
            0.15
            + (0.08 * hedge_matches)
            + (0.1 * vague_matches)
            + (0.15 if not response_text else 0.0),
        )
        ambiguity = _clamp(0.1 + (0.12 * vague_matches) + (0.1 if hedge_matches else 0.0))

        if reasoning is not None:
            if reasoning.summary.clarification_required:
                conflicting.append(
                    "Reasoning flagged clarification but a response was produced",
                )
            for question in reasoning.open_questions[:3]:
                if question.importance >= 0.8:
                    missing.append(f"Unresolved: {question.question}")

        grounded = False
        if context is not None:
            grounded = (
                context.memories is not None
                or bool(context.verified_knowledge)
                or context.world_model is not None
            )
            if not grounded and specific_facts >= 1:
                assumptions.append(
                    "Response states specific facts without grounded context",
                )

        hallucination_score = _clamp(
            0.1
            + (0.15 * absolute_matches)
            + (0.2 if specific_facts >= 2 and not grounded else 0.0)
            + (0.15 if reasoning is None and specific_facts >= 1 else 0.0),
        )

        if reasoning is not None:
            confidence = _clamp(
                reasoning.summary.confidence_score
                - (0.05 * len(missing))
                - (0.1 * hallucination_score),
            )
            quality_score = reasoning.summary.reasoning_quality_score
        else:
            confidence = _clamp(0.65 - uncertainty - (0.1 * hallucination_score))
            quality_score = _clamp(0.55 - (0.1 * len(missing)))

        clarification = (
            len(missing) >= 2
            or confidence < 0.5
            or hallucination_score >= 0.6
            or (reasoning is not None and reasoning.summary.clarification_required)
        )

        recommendation = self._build_recommendation(
            confidence=confidence,
            clarification_required=clarification,
            target="response",
            factors=(
                f"Response length: {len(response_text)} chars",
                f"Hedging signals: {hedge_matches}",
                f"Absolute claims: {absolute_matches}",
            ),
        )

        report = MetaCognitionReport(
            id=new_meta_id(),
            evaluation_target="response",
            confidence_score=confidence,
            uncertainty_score=uncertainty,
            ambiguity_score=ambiguity,
            missing_information=tuple(dict.fromkeys(missing)),
            assumptions=tuple(dict.fromkeys(assumptions)),
            conflicting_evidence=tuple(dict.fromkeys(conflicting)),
            hallucination_risk=_risk_from_score(hallucination_score),
            clarification_required=clarification,
            reasoning_quality=_quality_from_score(quality_score),
            recommendation=recommendation,
            message=message or (reasoning.message if reasoning else ""),
            sources={
                "response_length": len(response_text),
                "hedge_count": hedge_matches,
                "absolute_claim_count": absolute_matches,
                "specific_fact_count": specific_facts,
                "reasoning_provided": reasoning is not None,
                "context_provided": context is not None,
                "grounded_in_context": grounded,
            },
        )
        self._last_report = report
        return report

    def requires_clarification(self, report: MetaCognitionReport | None = None) -> bool:
        """Return whether the evaluated artifact needs user clarification."""
        target = report or self._last_report
        if target is None:
            return False
        return target.clarification_required

    def confidence(self, report: MetaCognitionReport | None = None) -> float:
        """Return confidence score from the last or supplied report."""
        target = report or self._last_report
        if target is None:
            return 0.0
        return target.confidence_score

    def export_report(self, report: MetaCognitionReport | None = None) -> dict[str, Any]:
        """Export a meta-cognition report as JSON-serializable data."""
        target = report or self._last_report
        if target is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "report": None,
                "message": "No meta-cognition report available",
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "report": target.to_dict(),
        }

    def get_last_report(self) -> MetaCognitionReport | None:
        """Return the most recently produced report."""
        return self._last_report

    # --- Private evaluation helpers ---

    def _detect_reasoning_conflicts(self, reasoning: ReasoningResult) -> list[str]:
        conflicts: list[str] = []
        if len(reasoning.alternatives) >= 2:
            scores = [alt.confidence for alt in reasoning.alternatives[:3]]
            if max(scores) - min(scores) < 0.08:
                conflicts.append(
                    "Top alternatives have near-equal confidence — tradeoff unresolved",
                )
        high_risks = [r for r in reasoning.risks if r.severity in {"high", "critical"}]
        if high_risks and reasoning.recommendation.confidence >= 0.8:
            conflicts.append(
                "High-severity risks coexist with high recommendation confidence",
            )
        if reasoning.recommendation.confidence < 0.5 and not reasoning.open_questions:
            conflicts.append(
                "Low recommendation confidence without documented open questions",
            )
        return conflicts

    def _uncertainty_from_reasoning(
        self,
        reasoning: ReasoningResult,
        unvalidated_assumptions: list[str],
    ) -> float:
        open_weight = min(0.4, 0.08 * len(reasoning.open_questions))
        assumption_weight = min(0.3, 0.05 * len(unvalidated_assumptions))
        risk_weight = min(0.2, 0.04 * len(reasoning.risks))
        alt_spread = 0.0
        if len(reasoning.alternatives) >= 2:
            scores = sorted(alt.confidence for alt in reasoning.alternatives[:3])
            alt_spread = max(0.0, 0.15 - (scores[-1] - scores[0]))
        return _clamp(0.1 + open_weight + assumption_weight + risk_weight + alt_spread)

    def _ambiguity_from_reasoning(self, reasoning: ReasoningResult) -> float:
        objective_len = len(reasoning.understanding.objective)
        score = 0.15
        if objective_len < 20:
            score += 0.2
        if reasoning.summary.domain.value == "general":
            score += 0.15
        if reasoning.understanding.requested_output in {"detect", "analyze"}:
            score += 0.05
        if len(reasoning.understanding.constraints) >= 3:
            score += 0.1
        return _clamp(score)

    def _context_missing_items(self, context: CognitiveContext) -> list[str]:
        missing: list[str] = []
        if not context.message.strip():
            missing.append("No request message in cognitive context")
        if context.world_model is None:
            missing.append("World Model snapshot not available in context")
        if context.memories is None:
            missing.append("Memory retrieval was not performed")
        elif not (
            context.memories.has_matches or bool(context.memories.text.strip())
        ):
            missing.append("No relevant memories retrieved for this request")
        if not context.verified_knowledge:
            missing.append("No verified knowledge matched this request")
        if context.architecture is None and context.build_mode.value in {
            "project",
            "code_task",
        }:
            missing.append("Architecture context missing for project/code task")
        return missing

    def _context_uncertainty_penalty(self, context: CognitiveContext) -> float:
        penalty = 0.0
        if context.world_model is None:
            penalty += 0.15
        if context.memories is None:
            penalty += 0.1
        if not context.verified_knowledge:
            penalty += 0.05
        if context.executive_priorities is None:
            penalty += 0.05
        return _clamp(penalty)

    def _hallucination_score_reasoning(
        self,
        reasoning: ReasoningResult,
        context: CognitiveContext | None,
        assumptions: list[str],
    ) -> float:
        score = 0.1
        if len(assumptions) >= 3:
            score += 0.2
        unvalidated = [a for a in reasoning.assumptions if not a.validated]
        if len(unvalidated) >= 2:
            score += 0.15
        if context is None:
            score += 0.2
        elif context.memories is None and not context.verified_knowledge:
            score += 0.15
        if not reasoning.context_sources:
            score += 0.1
        if reasoning.recommendation.confidence >= 0.85 and len(reasoning.steps) < 3:
            score += 0.1
        return _clamp(score)

    def _build_recommendation(
        self,
        *,
        confidence: float,
        clarification_required: bool,
        target: str,
        factors: tuple[str, ...],
    ) -> MetaCognitionRecommendation:
        strength = _strength_from_confidence(confidence)
        if clarification_required:
            return MetaCognitionRecommendation(
                strength=RecommendationStrength.WEAK,
                summary=f"Request clarification before finalizing {target}",
                factors=factors,
                proceed=False,
            )
        if strength == RecommendationStrength.STRONG:
            summary = f"{target.capitalize()} quality is sufficient to proceed"
        elif strength == RecommendationStrength.MODERATE:
            summary = f"{target.capitalize()} is acceptable with noted caveats"
        else:
            summary = f"{target.capitalize()} quality is weak — review before sending"
        return MetaCognitionRecommendation(
            strength=strength,
            summary=summary,
            factors=factors,
            proceed=strength != RecommendationStrength.WEAK,
        )

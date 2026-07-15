# =====================================
# Titan Reasoning Engine
# =====================================

"""Multi-step reasoning engine — structured thinking before planning or execution.

Analyzes complex requests through six stages: understand, context, decompose,
alternatives, evaluate, recommend. Never executes tools. Does not replace
Executive Function — produces ``ReasoningResult`` for downstream consumers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from brain.cognitive_context_builder import CognitiveContext, CognitiveContextBuilder
from brain.reasoning_models import (
    ReasoningAlternative,
    ReasoningAssumption,
    ReasoningDomain,
    ReasoningQuestion,
    ReasoningRecommendation,
    ReasoningResult,
    ReasoningRisk,
    ReasoningStage,
    ReasoningStep,
    ReasoningSummary,
    ReasoningUrgency,
    RequestUnderstanding,
    new_reasoning_id,
)

if TYPE_CHECKING:
    from brain.workspace_awareness import WorkspaceSnapshot

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{2,}", re.IGNORECASE)

_DOMAIN_KEYWORDS: dict[ReasoningDomain, tuple[str, ...]] = {
    ReasoningDomain.TRADING: (
        "trading", "trade", "broker", "market", "position", "backtest",
        "rithmic", "apex", "order", "portfolio",
    ),
    ReasoningDomain.ARCHITECTURE: (
        "architecture", "architectural", "design", "structure", "layer",
        "module boundary", "dependency graph",
    ),
    ReasoningDomain.CODE: (
        "code", "function", "class", "refactor", "implement", "patch",
        "module", "symbol", "caller", "dependency",
    ),
    ReasoningDomain.PLANNING: (
        "plan", "goal", "roadmap", "milestone", "sprint", "decompose",
        "strategy", "objective",
    ),
    ReasoningDomain.AUTOMATION: (
        "automate", "automation", "schedule", "workflow", "pipeline",
    ),
    ReasoningDomain.RESEARCH: (
        "research", "search", "find", "lookup", "investigate", "web",
    ),
    ReasoningDomain.MISSION: (
        "mission", "focus", "priority", "blocked", "continue", "next step",
    ),
    ReasoningDomain.WORKSPACE: (
        "workspace", "project", "file", "folder", "repository", "repo",
    ),
    ReasoningDomain.SOFTWARE: (
        "feature", "build", "ship", "deploy", "test", "release", "bug",
        "fix", "develop", "integration",
    ),
}

_URGENCY_KEYWORDS: dict[ReasoningUrgency, tuple[str, ...]] = {
    ReasoningUrgency.CRITICAL: ("critical", "urgent", "asap", "immediately", "now", "critique"),
    ReasoningUrgency.HIGH: ("soon", "priority", "important", "quickly", "fast"),
    ReasoningUrgency.LOW: ("later", "eventually", "when possible", "low priority"),
}

_OUTPUT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "compare": ("compare", "comparison", "versus", "vs", "options", "alternatives"),
    "analyze": ("analyze", "analyse", "analysis", "evaluate", "assess", "review"),
    "recommend": ("recommend", "suggest", "should i", "best way", "safest"),
    "explain": ("explain", "what is", "how does", "describe", "why"),
    "implement": ("implement", "build", "create", "add", "develop"),
    "detect": ("missing", "what information", "what do i need", "contradict"),
    "risk": ("risk", "risks", "danger", "safe", "safest"),
}

_DECOMPOSITION_TEMPLATES: dict[ReasoningDomain, tuple[tuple[str, str], ...]] = {
    ReasoningDomain.SOFTWARE: (
        ("Architecture", "Define boundaries and integration points"),
        ("Dependencies", "Identify upstream/downstream modules and tools"),
        ("Risks", "Surface breaking changes and rollback needs"),
        ("Testing", "Plan validation and regression coverage"),
        ("Deployment", "Consider rollout, flags, and monitoring"),
    ),
    ReasoningDomain.ARCHITECTURE: (
        ("Current state", "Map existing modules and boundaries"),
        ("Constraints", "Identify non-negotiables and invariants"),
        ("Options", "Compare structural approaches"),
        ("Impact", "Assess migration and compatibility"),
        ("Validation", "Define proof points for the chosen design"),
    ),
    ReasoningDomain.CODE: (
        ("Scope", "Pinpoint affected symbols and files"),
        ("Dependencies", "Trace callers and imports"),
        ("Change strategy", "Choose minimal vs comprehensive edit"),
        ("Testing", "Define verification steps"),
        ("Review", "Plan human review and rollback"),
    ),
    ReasoningDomain.PLANNING: (
        ("Goal clarity", "Normalize objective and success criteria"),
        ("Decomposition", "Break into projects and milestones"),
        ("Dependencies", "Order work and identify blockers"),
        ("Resources", "Tools, permissions, and skills needed"),
        ("Timeline", "Estimate effort and parallel opportunities"),
    ),
    ReasoningDomain.TRADING: (
        ("Strategy fit", "Align with risk policy and capital limits"),
        ("Market context", "Identify data and execution requirements"),
        ("Risk controls", "Stops, sizing, and paper-trading default"),
        ("Backtesting", "Validation before live execution"),
        ("Monitoring", "Alerts and kill-switch considerations"),
    ),
}

_DEFAULT_DECOMPOSITION: tuple[tuple[str, str], ...] = (
    ("Understand", "Clarify objective and constraints"),
    ("Context", "Gather workspace, memory, and mission signals"),
    ("Options", "Generate candidate approaches"),
    ("Evaluate", "Compare tradeoffs and risks"),
    ("Recommend", "Select strategy and surface open questions"),
)


class ReasoningEngine:
    """Structured multi-step reasoning — analysis only, no tool execution."""

    def __init__(
        self,
        *,
        cognitive_context_builder: CognitiveContextBuilder | None = None,
    ) -> None:
        self._cognitive_context_builder = cognitive_context_builder

    def attach_context_builder(self, builder: CognitiveContextBuilder) -> None:
        """Wire the shared Cognitive Context Builder from the composition root."""
        self._cognitive_context_builder = builder

    # --- Public API ---

    def reason(
        self,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        compare_mode: bool = False,
        explicit_options: tuple[str, ...] | None = None,
        project_focus: bool = False,
    ) -> ReasoningResult:
        """Run the full six-stage reasoning pipeline for *message*."""
        request = (message or "").strip()

        # Stage 1 — Understand
        understanding = self._understand_request(request, project_focus=project_focus)

        # Stage 2 — Context gathering (unified CognitiveContext only)
        context = self._gather_context(
            request,
            understanding=understanding,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

        # Stage 3 — Decompose
        steps = self._decompose_problem(understanding, context)

        # Stage 4 — Alternatives
        alternatives = self._generate_alternatives(
            understanding,
            context,
            steps,
            compare_mode=compare_mode or understanding.requested_output == "compare",
            explicit_options=explicit_options,
        )

        # Stage 5 — Evaluate & rank
        ranked = self._evaluate_alternatives(alternatives, understanding, context)

        # Risks, assumptions, questions
        risks = self._identify_risks(understanding, context, ranked)
        assumptions = self._identify_assumptions(understanding, context)
        questions = self._identify_open_questions(understanding, context, ranked)

        # Stage 6 — Recommend
        recommendation = self._build_recommendation(ranked, understanding, context)
        recommended_tools = self._recommend_tools(request, understanding, context)

        scores = self._compute_scores(
            understanding,
            context,
            ranked,
            questions,
            steps,
        )
        summary = ReasoningSummary(
            objective=understanding.objective,
            domain=understanding.domain,
            urgency=understanding.urgency,
            requested_output=understanding.requested_output,
            constraints=understanding.constraints,
            confidence_score=scores["confidence"],
            reasoning_quality_score=scores["quality"],
            completeness_score=scores["completeness"],
            clarification_required=len(questions) > 0 and scores["completeness"] < 0.75,
            headline=recommendation.strategy[:200],
        )

        result = ReasoningResult(
            message=request,
            understanding=understanding,
            summary=summary,
            steps=steps,
            alternatives=ranked,
            risks=risks,
            assumptions=assumptions,
            open_questions=questions,
            recommendation=recommendation,
            recommended_tools=recommended_tools,
            context_sources=context.sources,
        )
        logger.info(
            "ReasoningEngine completed domain=%s confidence=%.2f alternatives=%d "
            "questions=%d tools_recommended=%d",
            understanding.domain.value,
            summary.confidence_score,
            len(ranked),
            len(questions),
            len(recommended_tools),
        )
        return result

    def compare_options(
        self,
        message: str,
        options: tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> ReasoningResult:
        """Compare explicit or generated strategy options."""
        return self.reason(
            message,
            compare_mode=True,
            explicit_options=options,
            **kwargs,
        )

    def evaluate_request(self, message: str, **kwargs: Any) -> ReasoningResult:
        """Evaluate a request holistically — alias for ``reason``."""
        return self.reason(message, **kwargs)

    def detect_missing_information(
        self,
        message: str,
        **kwargs: Any,
    ) -> tuple[ReasoningQuestion, ...]:
        """Return open questions / missing information for *message*."""
        result = self.reason(message, **kwargs)
        return result.open_questions

    def recommend_strategy(
        self,
        message: str,
        **kwargs: Any,
    ) -> ReasoningRecommendation:
        """Return only the final recommendation."""
        return self.reason(message, **kwargs).recommendation

    def reason_about_project(
        self,
        message: str,
        **kwargs: Any,
    ) -> ReasoningResult:
        """Reason with project/architecture context emphasized."""
        return self.reason(message, project_focus=True, **kwargs)

    # --- Stage 1: Understand ---

    def _understand_request(
        self,
        request: str,
        *,
        project_focus: bool = False,
    ) -> RequestUnderstanding:
        normalized = " ".join(request.lower().split())
        tokens = tuple(_TOKEN_RE.findall(normalized))

        domain = self._classify_domain(tokens, normalized, project_focus=project_focus)
        urgency = self._detect_urgency(tokens, normalized)
        requested_output = self._detect_requested_output(normalized)
        constraints = self._extract_constraints(normalized)
        objective = self._extract_objective(request, domain)

        return RequestUnderstanding(
            objective=objective,
            constraints=constraints,
            urgency=urgency,
            domain=domain,
            requested_output=requested_output,
            raw_message=request,
        )

    def _classify_domain(
        self,
        tokens: tuple[str, ...],
        text: str,
        *,
        project_focus: bool = False,
    ) -> ReasoningDomain:
        if project_focus:
            return ReasoningDomain.ARCHITECTURE
        token_set = set(tokens)
        best = ReasoningDomain.GENERAL
        best_score = 0
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text or kw in token_set)
            if score > best_score:
                best_score = score
                best = domain
        return best

    def _detect_urgency(
        self,
        tokens: tuple[str, ...],
        text: str,
    ) -> ReasoningUrgency:
        for level in (ReasoningUrgency.CRITICAL, ReasoningUrgency.HIGH, ReasoningUrgency.LOW):
            if any(kw in text for kw in _URGENCY_KEYWORDS[level]):
                return level
        return ReasoningUrgency.NORMAL

    def _detect_requested_output(self, text: str) -> str:
        for output_type, keywords in _OUTPUT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return output_type
        if "?" in text:
            return "explain"
        return "recommend"

    def _extract_constraints(self, text: str) -> tuple[str, ...]:
        constraints: list[str] = []
        patterns = (
            r"\b(?:must|do not|don't|cannot|can't|without|only|never)\b[^.?!]{0,80}",
            r"\b(?:ne pas|sans|jamais|uniquement|obligatoire)\b[^.?!]{0,80}",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                snippet = match.group(0).strip()
                if len(snippet) > 8:
                    constraints.append(snippet[:120])
        return tuple(constraints[:6])

    def _extract_objective(self, request: str, domain: ReasoningDomain) -> str:
        cleaned = request.strip()
        if not cleaned:
            return "No objective specified"
        if len(cleaned) <= 200:
            return cleaned
        return cleaned[:197] + "..."

    # --- Stage 2: Context ---

    def _gather_context(
        self,
        request: str,
        *,
        understanding: RequestUnderstanding,
        user: str | None,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
    ) -> CognitiveContext:
        builder = self._resolve_context_builder()
        return builder.build_for_request(
            request,
            user=user,
            project_id=project_id,
            workspace=workspace,
            understanding=understanding,
        )

    def _resolve_context_builder(self) -> CognitiveContextBuilder:
        if self._cognitive_context_builder is None:
            raise RuntimeError(
                "ReasoningEngine requires a CognitiveContextBuilder — "
                "wire via Brain composition root or attach_context_builder()",
            )
        return self._cognitive_context_builder

    # --- Stage 3: Decompose ---

    def _decompose_problem(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
    ) -> tuple[ReasoningStep, ...]:
        template = _DECOMPOSITION_TEMPLATES.get(
            understanding.domain,
            _DEFAULT_DECOMPOSITION,
        )
        steps: list[ReasoningStep] = []
        for order, (title, description) in enumerate(template, start=1):
            confidence = 0.75
            if context.architecture is not None and title.lower() in ("architecture", "current state"):
                confidence = 0.85
            if context.code_context and title.lower() in ("scope", "dependencies"):
                confidence = 0.82
            steps.append(
                ReasoningStep(
                    id=new_reasoning_id("step"),
                    title=title,
                    description=description,
                    stage=ReasoningStage.DECOMPOSE,
                    order=order,
                    confidence=confidence,
                ),
            )
        return tuple(steps)

    # --- Stage 4: Alternatives ---

    def _generate_alternatives(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
        steps: tuple[ReasoningStep, ...],
        *,
        compare_mode: bool = False,
        explicit_options: tuple[str, ...] | None = None,
    ) -> tuple[ReasoningAlternative, ...]:
        if explicit_options:
            return tuple(
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description=opt,
                    advantages=("Explicit user-provided option",),
                    disadvantages=("Requires full evaluation",),
                    estimated_complexity="unknown",
                    estimated_risk="medium",
                    confidence=0.6,
                )
                for opt in explicit_options
            )

        domain = understanding.domain
        alts: list[ReasoningAlternative] = []

        if domain == ReasoningDomain.ARCHITECTURE or compare_mode:
            alts.extend([
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Incremental refactor — minimal boundary changes",
                    advantages=(
                        "Lower blast radius",
                        "Easier rollback",
                        "Fits existing tests",
                    ),
                    disadvantages=(
                        "May preserve technical debt",
                        "Slower long-term clarity",
                    ),
                    estimated_complexity="medium",
                    estimated_risk="low",
                    confidence=0.78,
                ),
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Modular extraction — clear new boundaries",
                    advantages=(
                        "Better maintainability",
                        "Clearer ownership",
                    ),
                    disadvantages=(
                        "Higher upfront cost",
                        "Migration coordination",
                    ),
                    estimated_complexity="high",
                    estimated_risk="medium",
                    confidence=0.72,
                ),
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Status quo + documented constraints",
                    advantages=("Zero immediate risk", "No migration"),
                    disadvantages=("Does not resolve root issue",),
                    estimated_complexity="low",
                    estimated_risk="low",
                    confidence=0.65,
                ),
            ])
        elif domain == ReasoningDomain.TRADING:
            alts.extend([
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Paper trading validation first",
                    advantages=("No capital risk", "Full pipeline test"),
                    disadvantages=("No real fills", "Latency may differ"),
                    estimated_complexity="medium",
                    estimated_risk="low",
                    confidence=0.85,
                ),
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Limited live size with strict stops",
                    advantages=("Real market feedback",),
                    disadvantages=("Capital at risk", "Requires monitoring"),
                    estimated_complexity="high",
                    estimated_risk="high",
                    confidence=0.55,
                ),
            ])
        elif domain == ReasoningDomain.CODE:
            alts.extend([
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Minimal targeted change",
                    advantages=("Small diff", "Fast review", "Low regression risk"),
                    disadvantages=("May not address adjacent issues",),
                    estimated_complexity="low",
                    estimated_risk="low",
                    confidence=0.8,
                ),
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Comprehensive refactor with tests",
                    advantages=("Cleaner long-term state",),
                    disadvantages=("Larger scope", "More review time"),
                    estimated_complexity="high",
                    estimated_risk="medium",
                    confidence=0.68,
                ),
            ])
        else:
            alts.extend([
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Conservative step-by-step approach",
                    advantages=(
                        "Validates assumptions early",
                        "Aligns with Titan quality principles",
                    ),
                    disadvantages=("May take longer",),
                    estimated_complexity="medium",
                    estimated_risk="low",
                    confidence=0.78,
                ),
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Parallel exploration then converge",
                    advantages=("Compares approaches quickly",),
                    disadvantages=("Higher cognitive load", "Possible wasted effort"),
                    estimated_complexity="medium",
                    estimated_risk="medium",
                    confidence=0.7,
                ),
            ])

        if len(steps) >= 4 and not compare_mode:
            alts.append(
                ReasoningAlternative(
                    id=new_reasoning_id("alt"),
                    description="Defer until missing information is clarified",
                    advantages=("Avoids wrong assumptions",),
                    disadvantages=("Blocks immediate progress",),
                    estimated_complexity="low",
                    estimated_risk="low",
                    confidence=0.6,
                ),
            )

        return tuple(alts[:4] if not compare_mode else alts)

    # --- Stage 5: Evaluate ---

    def _evaluate_alternatives(
        self,
        alternatives: tuple[ReasoningAlternative, ...],
        understanding: RequestUnderstanding,
        context: CognitiveContext,
    ) -> tuple[ReasoningAlternative, ...]:
        scored: list[tuple[float, ReasoningAlternative]] = []
        tool_count = len(context.tool_candidates)
        has_architecture = context.architecture is not None
        mission_count = len(context.active_missions)

        for alt in alternatives:
            risk_score = {"low": 0.9, "medium": 0.65, "high": 0.35, "unknown": 0.5}.get(
                alt.estimated_risk,
                0.5,
            )
            complexity_penalty = {"low": 0.1, "medium": 0.05, "high": 0.0, "unknown": 0.02}.get(
                alt.estimated_complexity,
                0.0,
            )
            tool_bonus = min(0.1, tool_count * 0.02)
            arch_bonus = 0.08 if has_architecture else 0.0
            mission_bonus = 0.05 if mission_count > 0 else 0.0
            urgency_boost = {
                ReasoningUrgency.CRITICAL: -0.05,
                ReasoningUrgency.HIGH: 0.0,
                ReasoningUrgency.NORMAL: 0.02,
                ReasoningUrgency.LOW: 0.05,
            }.get(understanding.urgency, 0.0)

            if "defer" in alt.description.lower():
                defer_penalty = -0.15 if understanding.urgency != ReasoningUrgency.LOW else 0.1
            else:
                defer_penalty = 0.0

            total = (
                alt.confidence * 0.4
                + risk_score * 0.25
                + complexity_penalty
                + tool_bonus
                + arch_bonus
                + mission_bonus
                + urgency_boost
                + defer_penalty
            )
            scores = {
                "risk": risk_score,
                "tool_availability": min(1.0, tool_count / 3.0),
                "architecture_fit": 0.85 if has_architecture else 0.5,
                "mission_relevance": min(1.0, mission_count / 2.0),
                "maintainability": 0.8 if "maintain" in alt.description.lower() else 0.65,
                "total": total,
            }
            scored.append(
                (
                    total,
                    replace(alt, scores=scores),
                ),
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        ranked: list[ReasoningAlternative] = []
        for rank, (_, alt) in enumerate(scored, start=1):
            ranked.append(replace(alt, rank=rank))
        return tuple(ranked)

    # --- Risks, assumptions, questions ---

    def _identify_risks(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
        alternatives: tuple[ReasoningAlternative, ...],
    ) -> tuple[ReasoningRisk, ...]:
        risks: list[ReasoningRisk] = []
        if understanding.domain == ReasoningDomain.TRADING:
            risks.append(
                ReasoningRisk(
                    id=new_reasoning_id("risk"),
                    summary="Live trading without paper validation exposes capital",
                    severity="high",
                    mitigation="Default to paper/simulation mode first",
                ),
            )
        if context.architecture is None and understanding.domain in (
            ReasoningDomain.ARCHITECTURE,
            ReasoningDomain.SOFTWARE,
        ):
            risks.append(
                ReasoningRisk(
                    id=new_reasoning_id("risk"),
                    summary="Architectural context unavailable — decisions may miss boundaries",
                    severity="medium",
                    mitigation="Run Project Intelligence analyze_project first",
                ),
            )
        missions = context.active_missions
        if len(missions) > 3:
            risks.append(
                ReasoningRisk(
                    id=new_reasoning_id("risk"),
                    summary="Multiple active missions may compete for attention",
                    severity="medium",
                    mitigation="Consult Executive Function for focus recommendation",
                ),
            )
        if alternatives and alternatives[0].estimated_risk == "high":
            risks.append(
                ReasoningRisk(
                    id=new_reasoning_id("risk"),
                    summary="Top-ranked alternative carries elevated risk",
                    severity="high",
                    mitigation="Add explicit rollback plan and human confirmation",
                ),
            )
        if "contradict" in understanding.raw_message.lower():
            risks.append(
                ReasoningRisk(
                    id=new_reasoning_id("risk"),
                    summary="Potential contradiction with prior decisions",
                    severity="medium",
                    mitigation="Cross-check memory and mission history",
                ),
            )
        return tuple(risks)

    def _identify_assumptions(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
    ) -> tuple[ReasoningAssumption, ...]:
        assumptions: list[ReasoningAssumption] = [
            ReasoningAssumption(
                id=new_reasoning_id("assume"),
                statement="User objective is accurately captured from the request text",
                confidence=0.85 if len(understanding.objective) > 10 else 0.55,
            ),
        ]
        workspace = context.active_workspace
        if workspace is not None:
            assumptions.append(
                ReasoningAssumption(
                    id=new_reasoning_id("assume"),
                    statement="Workspace snapshot reflects current project state",
                    confidence=0.8,
                    validated=True,
                ),
            )
        if understanding.domain == ReasoningDomain.TRADING:
            assumptions.append(
                ReasoningAssumption(
                    id=new_reasoning_id("assume"),
                    statement="Risk limits and paper-trading defaults are acceptable",
                    confidence=0.75,
                ),
            )
        return tuple(assumptions)

    def _identify_open_questions(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
        alternatives: tuple[ReasoningAlternative, ...],
    ) -> tuple[ReasoningQuestion, ...]:
        questions: list[ReasoningQuestion] = []
        if len(understanding.objective) < 15:
            questions.append(
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="What is the precise success criteria for this request?",
                    importance=0.9,
                ),
            )
        if understanding.requested_output == "compare" and len(alternatives) < 2:
            questions.append(
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="Which specific options should be compared?",
                    importance=0.85,
                    category="clarification",
                ),
            )
        if understanding.domain == ReasoningDomain.TRADING:
            questions.append(
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="Is paper trading acceptable before any live execution?",
                    importance=0.95,
                    category="risk",
                ),
            )
        if context.memories is None and "remember" not in understanding.raw_message.lower():
            if understanding.requested_output == "detect":
                questions.append(
                    ReasoningQuestion(
                        id=new_reasoning_id("q"),
                        question="Are there prior decisions or constraints stored in memory?",
                        importance=0.7,
                    ),
                )
        if understanding.constraints and any("without" in c for c in understanding.constraints):
            questions.append(
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="Are the stated constraints hard requirements or preferences?",
                    importance=0.75,
                    category="constraints",
                ),
            )
        return tuple(questions)

    # --- Stage 6: Recommend ---

    def _build_recommendation(
        self,
        ranked: tuple[ReasoningAlternative, ...],
        understanding: RequestUnderstanding,
        context: CognitiveContext,
    ) -> ReasoningRecommendation:
        if not ranked:
            return ReasoningRecommendation(
                strategy="Gather more context before recommending a strategy",
                supporting_arguments=("Insufficient alternatives generated",),
                confidence=0.4,
            )
        best = ranked[0]
        arguments: list[str] = [
            f"Highest composite score among {len(ranked)} alternatives",
            f"Estimated risk: {best.estimated_risk}",
            f"Domain: {understanding.domain.value}",
        ]
        if best.advantages:
            arguments.append(f"Key advantage: {best.advantages[0]}")
        if context.architecture is not None:
            arguments.append("Architecture context was available for evaluation")
        if understanding.urgency == ReasoningUrgency.CRITICAL:
            arguments.append("Urgency favors actionable low-risk path")

        return ReasoningRecommendation(
            strategy=best.description,
            supporting_arguments=tuple(arguments[:6]),
            confidence=min(0.95, best.confidence + 0.05),
            selected_alternative_id=best.id,
        )

    def _recommend_tools(
        self,
        request: str,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
    ) -> tuple[str, ...]:
        """Recommend tool ids only — never execute."""
        candidates = context.tool_candidates
        names: list[str] = []
        for item in candidates[:5]:
            tool_id = getattr(item, "tool_id", None) or getattr(item, "id", None)
            if tool_id and tool_id not in names:
                names.append(str(tool_id))
        return tuple(names)

    def _compute_scores(
        self,
        understanding: RequestUnderstanding,
        context: CognitiveContext,
        alternatives: tuple[ReasoningAlternative, ...],
        questions: tuple[ReasoningQuestion, ...],
        steps: tuple[ReasoningStep, ...],
    ) -> dict[str, float]:
        source_count = sum(1 for value in context.sources.values() if value)
        source_score = min(1.0, source_count / 5.0)
        alt_score = min(1.0, len(alternatives) / 3.0)
        step_score = min(1.0, len(steps) / 4.0)
        question_penalty = min(0.3, len(questions) * 0.08)

        completeness = max(0.0, source_score * 0.5 + alt_score * 0.3 + step_score * 0.2 - question_penalty)
        quality = max(0.0, alt_score * 0.4 + step_score * 0.35 + source_score * 0.25)
        confidence = 0.5
        if alternatives:
            confidence = alternatives[0].confidence * 0.6 + completeness * 0.25 + quality * 0.15
        if understanding.objective and len(understanding.objective) > 20:
            confidence = min(0.95, confidence + 0.05)

        return {
            "confidence": round(confidence, 3),
            "quality": round(quality, 3),
            "completeness": round(completeness, 3),
        }

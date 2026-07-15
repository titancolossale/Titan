# =====================================
# Titan Cognitive Loop
# =====================================

"""Structured cognition cycle — observations, thoughts, and recommendations only.

The Cognitive Loop decides *what Titan should think about* before action selection.
It never executes tools, runs background timers, or schedules autonomous work.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from brain.tool_intelligence import ToolExecutionPlan, ToolIntelligence, ToolIntent
from context.context_manager import ContextManager
from memory.memory_service import MemoryService
from memory.models import RetrievalResult

if TYPE_CHECKING:
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.proactive_intelligence import ProactiveSignal
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from core.mission_manager import MissionManager

logger = logging.getLogger(__name__)

_PRIORITY_RANK = {
    "CRITICAL": 0,
    "HIGH": 1,
    "NORMAL": 2,
    "LOW": 3,
}

_SESSION_OPEN_PATTERNS = (
    r"^(open|start|launch)\s+titan\b",
    r"^(ouvrir|demarrer|démarrer|lancer)\s+titan\b",
)
_NOTE_TOPIC_PATTERN = re.compile(
    r"\b(?:orr|obsidian|vault|notes?|note)\b",
    re.IGNORECASE,
)


class ThoughtPriority(str, Enum):
    """Relative urgency of a cognitive thought."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Observation:
    """A factual signal detected from current inputs."""

    id: str
    source: str
    summary: str
    detail: str
    importance: float
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "summary": self.summary,
            "detail": self.detail,
            "importance": round(self.importance, 3),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class Thought:
    """An evaluated cognitive unit with optional tool recommendation."""

    id: str
    source: str
    priority: ThoughtPriority
    confidence: float
    summary: str
    reasoning: str
    recommended_action: str
    requires_tools: tuple[str, ...]
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "priority": self.priority.value,
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "reasoning": self.reasoning,
            "recommended_action": self.recommended_action,
            "requires_tools": list(self.requires_tools),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class Recommendation:
    """Actionable guidance derived from prioritized thoughts."""

    id: str
    thought_id: str
    summary: str
    action: str
    priority: ThoughtPriority
    confidence: float
    requires_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "thought_id": self.thought_id,
            "summary": self.summary,
            "action": self.action,
            "priority": self.priority.value,
            "confidence": round(self.confidence, 3),
            "requires_tools": list(self.requires_tools),
        }


@dataclass(frozen=True)
class CognitiveLoopResult:
    """Output of one cognitive cycle for a single user turn."""

    message: str
    observations: tuple[Observation, ...]
    thoughts: tuple[Thought, ...]
    recommendations: tuple[Recommendation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "observations": [item.to_dict() for item in self.observations],
            "thoughts": [item.to_dict() for item in self.thoughts],
            "recommendations": [item.to_dict() for item in self.recommendations],
        }


@dataclass
class _ThoughtDraft:
    """Mutable builder used before deduplication and sorting."""

    source: str
    priority: ThoughtPriority
    confidence: float
    summary: str
    reasoning: str
    recommended_action: str
    requires_tools: tuple[str, ...] = field(default_factory=tuple)
    dedupe_key: str = ""


class CognitiveLoop:
    """Generate structured cognition from message, memory, and tool intelligence."""

    def __init__(
        self,
        memory_service: MemoryService,
        tool_intelligence: ToolIntelligence,
        context_manager: ContextManager | None = None,
        mission_manager: MissionManager | None = None,
        executive_function: ExecutiveFunction | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._tool_intelligence = tool_intelligence
        self._context_manager = context_manager
        self._mission_manager = mission_manager
        self._executive_function = executive_function
        self._workspace_awareness = workspace_awareness

    def run(
        self,
        message: str,
        *,
        user: str = "Nolan",
        project_id: str | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        workspace: WorkspaceSnapshot | None = None,
        proactive_signals: tuple[ProactiveSignal, ...] | None = None,
    ) -> CognitiveLoopResult:
        """Observe inputs, produce thoughts and recommendations — no tool execution."""
        now = _utc_now()
        stripped = message.strip()
        observations: list[Observation] = []
        drafts: list[_ThoughtDraft] = []

        workspace_snapshot = workspace
        if workspace_snapshot is None and self._workspace_awareness is not None:
            workspace_snapshot = self._workspace_awareness.get_workspace()

        evaluation = executive_evaluation
        if evaluation is None and self._executive_function is not None:
            evaluation = self._executive_function.evaluate_missions(
                stripped or message,
                user=user,
                project_id=project_id,
                now=now,
                workspace=workspace_snapshot,
            )

        observations.append(
            _observation(
                source="message",
                summary="User message received.",
                detail=stripped or "(empty session signal)",
                importance=0.35 if stripped else 0.55,
                timestamp=now,
            )
        )

        retrieval = self._memory_service.retrieve(user, stripped or message, project_id=project_id)
        session_notes = self._memory_service.get_session_notes()
        context_snapshot = self._load_context()
        tool_plan = self._tool_intelligence.plan(stripped or message)

        observations.extend(
            self._observe_memory(retrieval, now),
        )
        observations.extend(
            self._observe_session(session_notes, stripped, context_snapshot, now),
        )
        observations.extend(
            self._observe_workspace(workspace_snapshot, now),
        )
        observations.extend(
            self._observe_tool_plan(tool_plan, now),
        )
        observations.extend(
            self._observe_executive_focus(evaluation, now),
        )
        observations.extend(
            self._observe_missions(now),
        )
        observations.extend(
            self._observe_proactive_signals(proactive_signals, now),
        )

        memory_boost = _memory_priority_boost(retrieval)
        drafts.extend(
            self._thoughts_from_session(
                session_notes,
                stripped,
                context_snapshot,
                memory_boost,
            )
        )
        drafts.extend(
            self._thoughts_from_memory(retrieval, stripped, memory_boost),
        )
        drafts.extend(
            self._thoughts_from_workspace(workspace_snapshot, memory_boost),
        )
        drafts.extend(
            self._thoughts_from_tool_plan(tool_plan, retrieval, memory_boost),
        )
        drafts.extend(
            self._thoughts_from_executive_focus(evaluation, memory_boost),
        )
        drafts.extend(
            self._thoughts_from_missions(memory_boost),
        )

        thoughts = _finalize_thoughts(drafts, now)
        recommendations = _build_recommendations(thoughts)

        result = CognitiveLoopResult(
            message=message,
            observations=tuple(observations),
            thoughts=thoughts,
            recommendations=recommendations,
        )
        self._log_result(result)
        return result

    def _load_context(self) -> dict[str, str]:
        if self._context_manager is None:
            return {}
        return {
            "user": self._context_manager.current_user,
            "active_project": self._context_manager.active_project,
            "current_goal": self._context_manager.current_goal,
            "current_phase": self._context_manager.current_phase,
        }

    @staticmethod
    def _observe_memory(retrieval: RetrievalResult, timestamp: datetime) -> list[Observation]:
        if not retrieval.has_matches:
            return [
                _observation(
                    source="memory",
                    summary="No relevant long-term memory matched.",
                    detail=retrieval.text,
                    importance=0.2,
                    timestamp=timestamp,
                )
            ]
        count = len(retrieval.items)
        importance = min(0.95, 0.45 + count * 0.08)
        return [
            _observation(
                source="memory",
                summary=f"Relevant memory items detected ({count}).",
                detail="; ".join(retrieval.items[:5]),
                importance=importance,
                timestamp=timestamp,
            )
        ]

    @staticmethod
    def _observe_session(
        session_notes: list[str],
        message: str,
        context: dict[str, str],
        timestamp: datetime,
    ) -> list[Observation]:
        observations: list[Observation] = []
        if session_notes:
            observations.append(
                _observation(
                    source="session",
                    summary="Unread session notes detected.",
                    detail=session_notes[-1][:240],
                    importance=0.72,
                    timestamp=timestamp,
                )
            )

        if _is_session_open(message) and context.get("active_project"):
            observations.append(
                _observation(
                    source="context",
                    summary="Active project context available on session open.",
                    detail=f"Project: {context['active_project']}",
                    importance=0.68,
                    timestamp=timestamp,
                )
            )
        return observations

    @staticmethod
    def _observe_workspace(
        workspace: WorkspaceSnapshot | None,
        timestamp: datetime,
    ) -> list[Observation]:
        if workspace is None:
            return []

        observations = [
            _observation(
                source="workspace",
                summary=(
                    f"Workspace project « {workspace.current_project} » "
                    f"({workspace.project_language})."
                ),
                detail=workspace.summary or workspace.format_for_prompt(),
                importance=0.55,
                timestamp=timestamp,
            )
        ]
        if workspace.detected_modules:
            observations.append(
                _observation(
                    source="workspace",
                    summary=f"Detected {len(workspace.detected_modules)} module(s).",
                    detail=", ".join(workspace.detected_modules[:16]),
                    importance=0.4,
                    timestamp=timestamp,
                )
            )
        for recommendation in workspace.recommendations[:4]:
            importance = 0.7 if recommendation.kind in {
                "missing_documentation",
                "large_unfinished_feature",
                "mission_related_files",
            } else 0.5
            observations.append(
                _observation(
                    source="workspace",
                    summary=recommendation.summary,
                    detail=recommendation.detail,
                    importance=importance,
                    timestamp=timestamp,
                )
            )
        return observations

    @staticmethod
    def _thoughts_from_workspace(
        workspace: WorkspaceSnapshot | None,
        memory_boost: float,
    ) -> list[_ThoughtDraft]:
        if workspace is None:
            return []

        drafts: list[_ThoughtDraft] = [
            _ThoughtDraft(
                source="workspace",
                priority=_boost_priority(ThoughtPriority.NORMAL, memory_boost * 0.4),
                confidence=min(0.9, 0.62 + memory_boost * 0.1),
                summary=(
                    f"Use workspace context for « {workspace.current_project} » "
                    f"before deeper reasoning."
                ),
                reasoning=workspace.summary
                or f"{len(workspace.detected_modules)} modules detected.",
                recommended_action="Keep development workspace context in mind",
                dedupe_key=f"workspace:{workspace.current_project}",
            )
        ]
        for recommendation in workspace.recommendations[:3]:
            priority = ThoughtPriority.HIGH
            if recommendation.kind == "large_unfinished_feature":
                priority = ThoughtPriority.HIGH
            elif recommendation.kind == "missing_documentation":
                priority = ThoughtPriority.NORMAL
            drafts.append(
                _ThoughtDraft(
                    source="workspace",
                    priority=_boost_priority(priority, memory_boost * 0.3),
                    confidence=0.7,
                    summary=recommendation.summary,
                    reasoning=recommendation.detail,
                    recommended_action=f"Consider workspace signal: {recommendation.kind}",
                    dedupe_key=f"workspace_rec:{recommendation.kind}:{recommendation.summary[:40]}",
                )
            )
        return drafts

    @staticmethod
    def _observe_tool_plan(plan: ToolExecutionPlan, timestamp: datetime) -> list[Observation]:
        if plan.intent == ToolIntent.CONVERSATION:
            return [
                _observation(
                    source="tool_intelligence",
                    summary="Conversation-only request detected.",
                    detail=plan.intent_summary,
                    importance=0.25,
                    timestamp=timestamp,
                )
            ]

        if not plan.requires_tools:
            return [
                _observation(
                    source="tool_intelligence",
                    summary="No confident tool match for this request.",
                    detail=plan.reasoning_summary,
                    importance=0.3,
                    timestamp=timestamp,
                )
            ]

        observations: list[Observation] = []
        for selected in plan.selected_tools:
            detail = selected.reason
            if plan.intent == ToolIntent.COMPARE:
                summary = f"Tool candidate for comparison: {selected.tool_name}."
            elif selected.category == "notes":
                summary = "Relevant Obsidian notes may exist."
                detail = (
                    f"{selected.tool_name} selected for note retrieval "
                    f"(confidence {selected.confidence:.2f})."
                )
            elif selected.category == "web":
                summary = "Official documentation likely required."
                detail = (
                    f"{selected.tool_name} selected for web retrieval "
                    f"(confidence {selected.confidence:.2f})."
                )
            else:
                summary = f"Tool candidate identified: {selected.tool_name}."
            observations.append(
                _observation(
                    source="tool_intelligence",
                    summary=summary,
                    detail=detail,
                    importance=min(0.95, 0.5 + selected.confidence * 0.4),
                    timestamp=timestamp,
                )
            )
        return observations

    def _observe_executive_focus(
        self,
        evaluation: ExecutiveEvaluation | None,
        timestamp: datetime,
    ) -> list[Observation]:
        if evaluation is None:
            return []

        recommendation = evaluation.recommendation
        if recommendation.recommended_mission_id is None:
            return [
                _observation(
                    source="executive_function",
                    summary="Executive Function found no mission to prioritize.",
                    detail=evaluation.reasoning,
                    importance=0.2,
                    timestamp=timestamp,
                )
            ]

        importance = 0.7
        if recommendation.should_switch:
            importance = 0.9
        elif evaluation.blocked_missions:
            importance = 0.85

        summary = (
            f"Executive focus: « {recommendation.recommended_title} » "
            f"(score {recommendation.priority_score:.1f})."
        )
        if recommendation.should_switch:
            summary = (
                f"Executive recommends switching to « {recommendation.recommended_title} »."
            )

        return [
            _observation(
                source="executive_function",
                summary=summary,
                detail=evaluation.reasoning,
                importance=importance,
                timestamp=timestamp,
            )
        ]

    def _thoughts_from_executive_focus(
        self,
        evaluation: ExecutiveEvaluation | None,
        memory_boost: float,
    ) -> list[_ThoughtDraft]:
        if evaluation is None:
            return []

        recommendation = evaluation.recommendation
        if recommendation.recommended_mission_id is None:
            return []

        priority = ThoughtPriority.HIGH
        if recommendation.should_switch or evaluation.blocked_missions:
            priority = ThoughtPriority.CRITICAL
        priority = _boost_priority(priority, memory_boost * 0.4)

        action = (
            f"Switch mission focus to: {recommendation.recommended_title}"
            if recommendation.should_switch
            else f"Keep mission focus on: {recommendation.recommended_title}"
        )
        return [
            _ThoughtDraft(
                source="executive_function",
                priority=priority,
                confidence=min(0.93, 0.7 + recommendation.priority_score / 400),
                summary=action,
                reasoning=recommendation.reasoning,
                recommended_action=action,
                dedupe_key=(
                    f"executive_focus:{recommendation.recommended_mission_id}:"
                    f"{int(recommendation.should_switch)}"
                ),
            )
        ]

    def _observe_missions(self, timestamp: datetime) -> list[Observation]:
        if self._mission_manager is None:
            return []

        active = self._mission_manager.runtime.get_active_mission()
        if active is None:
            return [
                _observation(
                    source="mission",
                    summary="No active mission.",
                    detail="Mission runtime has no focused objective.",
                    importance=0.15,
                    timestamp=timestamp,
                )
            ]

        detail = (
            f"{active.title}: {active.progress_percent:.0f}% complete. "
            f"Current step: {active.current_step or 'none'}."
        )
        importance = 0.75 if active.state.value in {"RUNNING", "BLOCKED"} else 0.55
        return [
            _observation(
                source="mission",
                summary=f"Active mission « {active.title} » ({active.state.value}).",
                detail=detail,
                importance=importance,
                timestamp=timestamp,
            )
        ]

    def _observe_proactive_signals(
        self,
        signals: tuple[ProactiveSignal, ...] | None,
        timestamp: datetime,
    ) -> list[Observation]:
        """Read-only observations from Proactive Intelligence signals."""
        if not signals:
            return []
        observations: list[Observation] = []
        for signal in signals[:8]:
            observations.append(
                _observation(
                    source="proactive_intelligence",
                    summary=signal.summary,
                    detail=signal.detail,
                    importance=min(0.9, signal.importance),
                    timestamp=timestamp,
                )
            )
        return observations

    def _thoughts_from_missions(self, memory_boost: float) -> list[_ThoughtDraft]:
        if self._mission_manager is None:
            return []

        active = self._mission_manager.runtime.get_active_mission()
        if active is None:
            return []

        priority = ThoughtPriority.HIGH
        if active.state.value == "BLOCKED":
            priority = ThoughtPriority.CRITICAL
        elif active.state.value in {"WAITING", "PLANNING"}:
            priority = ThoughtPriority.NORMAL

        priority = _boost_priority(priority, memory_boost * 0.5)
        step = active.current_step or "next step"
        return [
            _ThoughtDraft(
                source="mission",
                priority=priority,
                confidence=min(0.92, 0.65 + active.progress_percent / 200),
                summary=f"Advance mission step: {step}.",
                reasoning=(
                    f"Mission « {active.title} » is {active.state.value} "
                    f"at {active.progress_percent:.0f}% progress."
                ),
                recommended_action=f"Focus on mission step: {step}",
                dedupe_key=f"mission_step:{active.id}:{step}",
            )
        ]

    @staticmethod
    def _thoughts_from_session(
        session_notes: list[str],
        message: str,
        context: dict[str, str],
        memory_boost: float,
    ) -> list[_ThoughtDraft]:
        drafts: list[_ThoughtDraft] = []
        project = context.get("active_project", "").strip()

        if session_notes and (_is_session_open(message) or not message.strip()):
            confidence = min(0.9, 0.62 + memory_boost * 0.15)
            drafts.append(
                _ThoughtDraft(
                    source="session",
                    priority=_boost_priority(ThoughtPriority.HIGH, memory_boost),
                    confidence=confidence,
                    summary="Review latest project notes.",
                    reasoning=(
                        "Session notes are pending review and the user opened Titan "
                        "or sent an empty turn signal."
                    ),
                    recommended_action="Review session notes before deeper reasoning.",
                    dedupe_key="review_session_notes",
                )
            )
        elif project and _is_session_open(message):
            drafts.append(
                _ThoughtDraft(
                    source="context",
                    priority=ThoughtPriority.NORMAL,
                    confidence=0.58,
                    summary=f"Review context for project {project}.",
                    reasoning="An active project is loaded at session start.",
                    recommended_action="Load project context and recent notes.",
                    dedupe_key=f"review_project:{project.lower()}",
                )
            )
        return drafts

    @staticmethod
    def _thoughts_from_memory(
        retrieval: RetrievalResult,
        message: str,
        memory_boost: float,
    ) -> list[_ThoughtDraft]:
        if not retrieval.has_matches:
            return []

        priority = ThoughtPriority.NORMAL
        if memory_boost >= 0.35:
            priority = ThoughtPriority.HIGH
        if memory_boost >= 0.55:
            priority = ThoughtPriority.CRITICAL

        note_signal = bool(_NOTE_TOPIC_PATTERN.search(message)) or any(
            "note" in item.lower() or "projet" in item.lower() or "project" in item.lower()
            for item in retrieval.items
        )
        requires_tools: tuple[str, ...] = ("obsidian",) if note_signal else tuple()
        action = (
            "Search Obsidian for matching notes before answering."
            if note_signal
            else "Incorporate retrieved memory into the response."
        )
        summary = (
            "Use Obsidian before answering."
            if note_signal
            else "Apply retrieved memory to the response."
        )

        return [
            _ThoughtDraft(
                source="memory",
                priority=priority,
                confidence=min(0.95, 0.5 + memory_boost),
                summary=summary,
                reasoning=(
                    f"Long-term memory returned {len(retrieval.items)} relevant item(s) "
                    "that should influence reasoning priority."
                ),
                recommended_action=action,
                requires_tools=requires_tools,
                dedupe_key="memory_influence",
            )
        ]

    @staticmethod
    def _thoughts_from_tool_plan(
        plan: ToolExecutionPlan,
        retrieval: RetrievalResult,
        memory_boost: float,
    ) -> list[_ThoughtDraft]:
        drafts: list[_ThoughtDraft] = []

        if plan.intent == ToolIntent.CONVERSATION:
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=ThoughtPriority.LOW,
                    confidence=plan.confidence,
                    summary="No action needed. Conversation only.",
                    reasoning=plan.intent_summary,
                    recommended_action="Respond conversationally without tool use.",
                    dedupe_key="conversation_only",
                )
            )
            return drafts

        tool_ids = {tool.tool_id for tool in plan.selected_tools}

        if "obsidian" in tool_ids:
            confidence = _tool_confidence(plan, "obsidian", memory_boost)
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=_tool_priority(confidence, memory_boost if retrieval.has_matches else 0.0),
                    confidence=confidence,
                    summary="Use Obsidian before answering.",
                    reasoning=(
                        "Tool Intelligence matched the Obsidian vault for note retrieval "
                        f"with intent {plan.intent.value}."
                    ),
                    recommended_action="Search or read relevant vault notes first.",
                    requires_tools=("obsidian",),
                    dedupe_key="tool:obsidian",
                )
            )

        if "browser" in tool_ids:
            confidence = _tool_confidence(plan, "browser", memory_boost)
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=_tool_priority(confidence, 0.0),
                    confidence=confidence,
                    summary="Browser should retrieve official docs.",
                    reasoning=(
                        "Tool Intelligence matched the browser for documentation or web "
                        f"content with intent {plan.intent.value}."
                    ),
                    recommended_action="Fetch official documentation before synthesizing.",
                    requires_tools=("browser",),
                    dedupe_key="tool:browser",
                )
            )

        for selected in plan.selected_tools:
            if selected.tool_id in {"obsidian", "browser"}:
                continue
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=ThoughtPriority.NORMAL,
                    confidence=selected.confidence,
                    summary=f"Consider {selected.tool_name} for this request.",
                    reasoning=selected.reason,
                    recommended_action=f"Plan actions via {selected.tool_id}.",
                    requires_tools=(selected.tool_id,),
                    dedupe_key=f"tool:{selected.tool_id}",
                )
            )

        if plan.intent == ToolIntent.COMPARE and {"obsidian", "browser"}.issubset(tool_ids):
            compare_confidence = min(0.95, plan.confidence + 0.05)
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=ThoughtPriority.HIGH,
                    confidence=compare_confidence,
                    summary="Compare vault notes with external documentation.",
                    reasoning=(
                        "Both Obsidian and browser tools were selected for a compare intent."
                    ),
                    recommended_action=(
                        "Retrieve notes and documentation, then synthesize differences."
                    ),
                    requires_tools=("obsidian", "browser"),
                    dedupe_key="compare_notes_docs",
                )
            )

        if not drafts and not plan.requires_tools:
            drafts.append(
                _ThoughtDraft(
                    source="tool_intelligence",
                    priority=ThoughtPriority.LOW,
                    confidence=plan.confidence,
                    summary="Clarify request before recommending tools.",
                    reasoning=plan.reasoning_summary,
                    recommended_action="Ask a clarifying question if needed.",
                    dedupe_key="clarify_request",
                )
            )

        return drafts

    @staticmethod
    def _log_result(result: CognitiveLoopResult) -> None:
        logger.info(
            "CognitiveLoop message=%r observations=%d thoughts=%d recommendations=%d",
            result.message,
            len(result.observations),
            len(result.thoughts),
            len(result.recommendations),
        )
        for observation in result.observations:
            logger.info(
                "CognitiveLoop observation id=%s source=%s importance=%.3f summary=%s",
                observation.id,
                observation.source,
                observation.importance,
                observation.summary,
            )
        for thought in result.thoughts:
            logger.info(
                (
                    "CognitiveLoop thought id=%s priority=%s confidence=%.3f "
                    "summary=%s tools=%s"
                ),
                thought.id,
                thought.priority.value,
                thought.confidence,
                thought.summary,
                list(thought.requires_tools),
            )
        for recommendation in result.recommendations:
            logger.info(
                (
                    "CognitiveLoop recommendation id=%s priority=%s confidence=%.3f "
                    "action=%s"
                ),
                recommendation.id,
                recommendation.priority.value,
                recommendation.confidence,
                recommendation.action,
            )


def _observation(
    *,
    source: str,
    summary: str,
    detail: str,
    importance: float,
    timestamp: datetime,
) -> Observation:
    return Observation(
        id=_new_id("obs"),
        source=source,
        summary=summary,
        detail=detail,
        importance=min(1.0, max(0.0, importance)),
        timestamp=timestamp,
    )


def _finalize_thoughts(drafts: list[_ThoughtDraft], timestamp: datetime) -> tuple[Thought, ...]:
    deduped = _dedupe_drafts(drafts)
    sorted_drafts = sorted(
        deduped,
        key=lambda item: (_PRIORITY_RANK[item.priority.value], -item.confidence),
    )
    thoughts: list[Thought] = []
    for draft in sorted_drafts:
        thoughts.append(
            Thought(
                id=_new_id("thought"),
                source=draft.source,
                priority=draft.priority,
                confidence=round(min(0.99, max(0.05, draft.confidence)), 3),
                summary=draft.summary,
                reasoning=draft.reasoning,
                recommended_action=draft.recommended_action,
                requires_tools=draft.requires_tools,
                timestamp=timestamp,
            )
        )
    return tuple(thoughts)


def _dedupe_drafts(drafts: list[_ThoughtDraft]) -> list[_ThoughtDraft]:
    """Merge duplicate thoughts by semantic identity, keeping the strongest candidate."""
    merged: dict[str, _ThoughtDraft] = {}
    for draft in drafts:
        key = _draft_semantic_key(draft)
        existing = merged.get(key)
        if existing is None:
            merged[key] = draft
            continue
        merged[key] = _merge_drafts(existing, draft)
    return list(merged.values())


def _draft_semantic_key(draft: _ThoughtDraft) -> str:
    tools = "|".join(sorted(draft.requires_tools))
    return f"{draft.summary.lower()}|{tools}"


def _merge_drafts(left: _ThoughtDraft, right: _ThoughtDraft) -> _ThoughtDraft:
    priority = left.priority if _PRIORITY_RANK[left.priority.value] <= _PRIORITY_RANK[right.priority.value] else right.priority
    confidence = max(left.confidence, right.confidence)
    tools = tuple(sorted(set(left.requires_tools) | set(right.requires_tools)))
    reasoning = left.reasoning if len(left.reasoning) >= len(right.reasoning) else right.reasoning
    return _ThoughtDraft(
        source=left.source if priority == left.priority else right.source,
        priority=priority,
        confidence=confidence,
        summary=left.summary,
        reasoning=reasoning,
        recommended_action=left.recommended_action or right.recommended_action,
        requires_tools=tools,
        dedupe_key=left.dedupe_key or right.dedupe_key,
    )


def _build_recommendations(thoughts: tuple[Thought, ...]) -> tuple[Recommendation, ...]:
    recommendations: list[Recommendation] = []
    for thought in thoughts:
        if thought.priority == ThoughtPriority.LOW and not thought.requires_tools:
            if "conversation" in thought.summary.lower():
                continue
        if thought.recommended_action:
            recommendations.append(
                Recommendation(
                    id=_new_id("rec"),
                    thought_id=thought.id,
                    summary=thought.summary,
                    action=thought.recommended_action,
                    priority=thought.priority,
                    confidence=thought.confidence,
                    requires_tools=thought.requires_tools,
                )
            )
    recommendations.sort(
        key=lambda item: (_PRIORITY_RANK[item.priority.value], -item.confidence),
    )
    return tuple(recommendations)


def _memory_priority_boost(retrieval: RetrievalResult) -> float:
    if not retrieval.has_matches:
        return 0.0
    return min(0.65, 0.15 + len(retrieval.items) * 0.08)


def _tool_confidence(plan: ToolExecutionPlan, tool_id: str, memory_boost: float) -> float:
    selected = next((tool for tool in plan.selected_tools if tool.tool_id == tool_id), None)
    base = selected.confidence if selected is not None else plan.confidence
    if memory_boost and tool_id == "obsidian":
        base = min(0.98, base + memory_boost * 0.25)
    return round(min(0.98, max(0.2, base)), 3)


def _tool_priority(confidence: float, memory_boost: float) -> ThoughtPriority:
    score = confidence + memory_boost * 0.35
    if score >= 0.85:
        return ThoughtPriority.CRITICAL
    if score >= 0.65:
        return ThoughtPriority.HIGH
    if score >= 0.4:
        return ThoughtPriority.NORMAL
    return ThoughtPriority.LOW


def _boost_priority(base: ThoughtPriority, boost: float) -> ThoughtPriority:
    if boost >= 0.55:
        return ThoughtPriority.CRITICAL
    if boost >= 0.35 and base.value != "CRITICAL":
        return ThoughtPriority.HIGH
    return base


def _is_session_open(message: str) -> bool:
    stripped = message.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    return any(re.search(pattern, lowered) for pattern in _SESSION_OPEN_PATTERNS)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

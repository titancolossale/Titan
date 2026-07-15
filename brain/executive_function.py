# =====================================
# Titan Executive Function
# =====================================

"""Executive decision layer — which mission deserves attention.

Read-only analysis only. Never executes tools, never runs cognition,
and never mutates mission persistence. Coordinates priorities before
the Cognitive Loop and Tool Execution Engine act.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.mission_models import Mission, MissionPriority, MissionState
from memory.models import RetrievalResult

if TYPE_CHECKING:
    from brain.long_term_planner import GoalPlan, PlanningRecommendation
    from brain.reasoning_models import ReasoningResult
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{3,}", re.IGNORECASE)

_PRIORITY_WEIGHTS: dict[MissionPriority, float] = {
    MissionPriority.CRITICAL: 40.0,
    MissionPriority.HIGH: 30.0,
    MissionPriority.NORMAL: 20.0,
    MissionPriority.LOW: 10.0,
}

_STATE_WEIGHTS: dict[MissionState, float] = {
    MissionState.BLOCKED: 35.0,
    MissionState.RUNNING: 28.0,
    MissionState.WAITING: 18.0,
    MissionState.READY: 16.0,
    MissionState.PLANNING: 14.0,
    MissionState.CREATED: 12.0,
    MissionState.FAILED: 0.0,
    MissionState.COMPLETED: 0.0,
    MissionState.CANCELLED: 0.0,
}

# Idle when no update for this many hours (WAITING / READY / CREATED).
_IDLE_HOURS = 24.0
# Cap age contribution so ancient missions do not dominate forever.
_MAX_AGE_HOURS = 168.0  # 7 days
_MAX_BLOCKED_HOURS = 72.0


@dataclass(frozen=True)
class MissionScoreBreakdown:
    """Weighted factor contributions for one mission evaluation."""

    priority: float
    age: float
    progress: float
    state: float
    relevance: float
    blocked_duration: float

    def to_dict(self) -> dict[str, float]:
        return {
            "priority": round(self.priority, 3),
            "age": round(self.age, 3),
            "progress": round(self.progress, 3),
            "state": round(self.state, 3),
            "relevance": round(self.relevance, 3),
            "blocked_duration": round(self.blocked_duration, 3),
        }


@dataclass(frozen=True)
class MissionEvaluation:
    """Scored snapshot of one active mission."""

    mission_id: str
    title: str
    state: MissionState
    priority: MissionPriority
    progress_percent: float
    priority_score: float
    is_blocked: bool
    is_idle: bool
    blocked_hours: float
    age_hours: float
    relevance: float
    reasoning: str
    breakdown: MissionScoreBreakdown
    is_current_focus: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "state": self.state.value,
            "priority": self.priority.value,
            "progress_percent": round(self.progress_percent, 2),
            "priority_score": round(self.priority_score, 3),
            "is_blocked": self.is_blocked,
            "is_idle": self.is_idle,
            "blocked_hours": round(self.blocked_hours, 3),
            "age_hours": round(self.age_hours, 3),
            "relevance": round(self.relevance, 3),
            "reasoning": self.reasoning,
            "breakdown": self.breakdown.to_dict(),
            "is_current_focus": self.is_current_focus,
        }


@dataclass(frozen=True)
class FocusRecommendation:
    """Recommended mission focus after ranking."""

    recommended_mission_id: str | None
    recommended_title: str | None
    current_mission_id: str | None
    should_switch: bool
    reasoning: str
    priority_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_mission_id": self.recommended_mission_id,
            "recommended_title": self.recommended_title,
            "current_mission_id": self.current_mission_id,
            "should_switch": self.should_switch,
            "reasoning": self.reasoning,
            "priority_score": round(self.priority_score, 3),
        }


@dataclass(frozen=True)
class ExecutiveEvaluation:
    """Full executive analysis for one attention cycle."""

    current_mission: Mission | None
    ranked_missions: tuple[MissionEvaluation, ...]
    recommendation: FocusRecommendation
    reasoning: str
    blocked_missions: tuple[MissionEvaluation, ...] = field(default_factory=tuple)
    idle_missions: tuple[MissionEvaluation, ...] = field(default_factory=tuple)
    workspace_summary: str | None = None

    @property
    def recommended_next_mission(self) -> MissionEvaluation | None:
        if not self.ranked_missions:
            return None
        return self.ranked_missions[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_mission": (
                {
                    "id": self.current_mission.id,
                    "title": self.current_mission.title,
                    "state": self.current_mission.state.value,
                    "priority": self.current_mission.priority.value,
                }
                if self.current_mission is not None
                else None
            ),
            "ranked_missions": [item.to_dict() for item in self.ranked_missions],
            "recommendation": self.recommendation.to_dict(),
            "reasoning": self.reasoning,
            "blocked_missions": [item.to_dict() for item in self.blocked_missions],
            "idle_missions": [item.to_dict() for item in self.idle_missions],
            "recommended_next_mission": (
                self.recommended_next_mission.to_dict()
                if self.recommended_next_mission is not None
                else None
            ),
            "workspace_summary": self.workspace_summary,
        }


class ExecutiveFunction:
    """Decide which mission should receive attention — read-only coordination."""

    def __init__(
        self,
        mission_manager: MissionManager,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
    ) -> None:
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._workspace_awareness = workspace_awareness

    def get_current_focus(self) -> Mission | None:
        """Return the mission currently marked as active focus (if non-terminal)."""
        return self._mission_manager.runtime.get_active_mission()

    def evaluate_missions(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        now: datetime | None = None,
        workspace: WorkspaceSnapshot | None = None,
        reasoning_result: ReasoningResult | None = None,
    ) -> ExecutiveEvaluation:
        """Rank all active missions and produce a focus recommendation.

        Completed / failed / cancelled missions are ignored (not listed as active).
        This method never mutates mission data and never executes tools.

        When *reasoning_result* is supplied, executive reasoning reuses the
        Reasoning Engine recommendation instead of duplicating general analysis.
        """
        timestamp = now or _utc_now()
        current = self.get_current_focus()
        active = list(self._mission_manager.runtime.list_active_missions())

        workspace_snapshot = workspace
        if workspace_snapshot is None and self._workspace_awareness is not None:
            workspace_snapshot = self._workspace_awareness.get_workspace()

        retrieval = self._retrieve_memory(message, user=user, project_id=project_id)
        evaluations = [
            self._evaluate_one(
                mission,
                message=message,
                retrieval=retrieval,
                current_id=current.id if current is not None else None,
                now=timestamp,
                workspace=workspace_snapshot,
            )
            for mission in active
        ]
        ranked = tuple(sorted(evaluations, key=_rank_key))

        blocked = tuple(item for item in ranked if item.is_blocked)
        idle = tuple(item for item in ranked if item.is_idle)
        recommendation = self._build_recommendation(
            ranked,
            current,
            reasoning_result=reasoning_result,
        )
        reasoning = self._build_overall_reasoning(
            ranked,
            current,
            recommendation,
            blocked,
            idle,
            reasoning_result=reasoning_result,
        )
        workspace_summary = (
            workspace_snapshot.summary if workspace_snapshot is not None else None
        )
        if workspace_summary and reasoning_result is None:
            reasoning = f"{reasoning} Workspace: {workspace_summary}"

        result = ExecutiveEvaluation(
            current_mission=current,
            ranked_missions=ranked,
            recommendation=recommendation,
            reasoning=reasoning,
            blocked_missions=blocked,
            idle_missions=idle,
            workspace_summary=workspace_summary,
        )
        logger.info(
            "ExecutiveFunction evaluated %d active mission(s); "
            "recommended=%s should_switch=%s",
            len(ranked),
            recommendation.recommended_mission_id,
            recommendation.should_switch,
        )
        return result

    def recommend_focus(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        now: datetime | None = None,
        workspace: WorkspaceSnapshot | None = None,
    ) -> FocusRecommendation:
        """Return only the focus recommendation for *message*."""
        return self.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            now=now,
            workspace=workspace,
        ).recommendation

    def recommend_next_from_goal_plan(self, plan: Any) -> Any:
        """Recommend what to work on next from a GoalPlan.

        Consumes a long-term ``GoalPlan`` and returns a ``PlanningRecommendation``.
        Never modifies the plan, never creates missions, never executes tools.
        """
        from brain.long_term_planner import (
            PlanningRecommendation,
            TaskStatus,
        )

        tasks = list(plan.all_tasks()) if hasattr(plan, "all_tasks") else []
        if not tasks:
            return PlanningRecommendation(
                summary="No tasks in goal plan — nothing to recommend",
                rationale="Empty GoalPlan",
                source="executive_function",
            )

        ready = [t for t in tasks if getattr(t, "status", None) == TaskStatus.READY]
        critical = [t for t in ready if getattr(t, "is_critical_path", False)]
        quick = [t for t in ready if getattr(t, "is_quick_win", False)]
        high_risk = [t for t in tasks if getattr(t, "is_high_risk", False)]

        # Prefer quick wins that unblock critical path, else critical ready, else any ready.
        next_task = None
        if quick:
            next_task = quick[0]
        elif critical:
            next_task = critical[0]
        elif ready:
            next_task = ready[0]
        else:
            # Fall back to first pending with no blockers.
            pending = [
                t
                for t in tasks
                if getattr(t, "status", None) == TaskStatus.PENDING
                and not getattr(t, "blocked_by", ())
            ]
            next_task = pending[0] if pending else tasks[0]

        current = self.get_current_focus()
        rationale_parts = [
            "Executive Function recommends next planned work without modifying the GoalPlan.",
        ]
        if current is not None:
            rationale_parts.append(
                f"Current mission focus remains « {current.title} » "
                "(planner proposals are not auto-started)."
            )
        if getattr(next_task, "is_critical_path", False):
            rationale_parts.append("Task is on the critical path.")
        if getattr(next_task, "is_quick_win", False):
            rationale_parts.append("Task is a low-risk quick win.")

        parallel = tuple(
            t.id
            for t in ready
            if t.id != next_task.id and getattr(t, "is_parallel_safe", False)
        )[:6]
        avoid = tuple(t.id for t in high_risk if t.id != next_task.id)[:6]

        return PlanningRecommendation(
            summary=f"Executive next work: {next_task.title}",
            next_task_id=next_task.id,
            next_task_title=next_task.title,
            rationale=" ".join(rationale_parts),
            parallel_task_ids=parallel,
            avoid_task_ids=avoid,
            source="executive_function",
        )

    def _retrieve_memory(
        self,
        message: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> RetrievalResult | None:
        if self._memory_service is None or not message.strip():
            return None
        resolved_user = user
        if resolved_user is None and self._context_manager is not None:
            resolved_user = self._context_manager.current_user
        if not resolved_user:
            resolved_user = "Nolan"
        resolved_project = project_id
        if resolved_project is None and self._context_manager is not None:
            resolved_project = self._context_manager.active_project or None
        return self._memory_service.retrieve(
            resolved_user,
            message,
            project_id=resolved_project,
        )

    def _evaluate_one(
        self,
        mission: Mission,
        *,
        message: str,
        retrieval: RetrievalResult | None,
        current_id: str | None,
        now: datetime,
        workspace: WorkspaceSnapshot | None = None,
    ) -> MissionEvaluation:
        age_hours = _hours_since(mission.created_at, now)
        idle_hours = _hours_since(mission.updated_at, now)
        blocked_hours = (
            _blocked_duration_hours(mission, now)
            if mission.state == MissionState.BLOCKED
            else 0.0
        )
        relevance = _relevance_score(mission, message, retrieval, workspace)

        priority_score = _PRIORITY_WEIGHTS.get(mission.priority, 20.0)
        age_score = min(age_hours / _MAX_AGE_HOURS, 1.0) * 10.0
        progress_score = _progress_score(mission.progress_percent)
        state_score = _STATE_WEIGHTS.get(mission.state, 10.0)
        relevance_score = relevance * 25.0
        blocked_score = min(blocked_hours / _MAX_BLOCKED_HOURS, 1.0) * 20.0
        if mission.state == MissionState.BLOCKED:
            blocked_score = max(blocked_score, 8.0)

        breakdown = MissionScoreBreakdown(
            priority=priority_score,
            age=age_score,
            progress=progress_score,
            state=state_score,
            relevance=relevance_score,
            blocked_duration=blocked_score,
        )
        total = (
            breakdown.priority
            + breakdown.age
            + breakdown.progress
            + breakdown.state
            + breakdown.relevance
            + breakdown.blocked_duration
        )

        is_blocked = mission.state == MissionState.BLOCKED
        is_idle = (
            not is_blocked
            and mission.state
            in {MissionState.WAITING, MissionState.READY, MissionState.CREATED}
            and idle_hours >= _IDLE_HOURS
        )
        # Mild idle boost so stalled work surfaces without overriding BLOCKED/CRITICAL.
        if is_idle:
            total += 6.0

        reasoning = _mission_reasoning(
            mission,
            total=total,
            relevance=relevance,
            is_blocked=is_blocked,
            is_idle=is_idle,
            blocked_hours=blocked_hours,
            idle_hours=idle_hours,
            age_hours=age_hours,
        )
        return MissionEvaluation(
            mission_id=mission.id,
            title=mission.title,
            state=mission.state,
            priority=mission.priority,
            progress_percent=mission.progress_percent,
            priority_score=total,
            is_blocked=is_blocked,
            is_idle=is_idle,
            blocked_hours=blocked_hours,
            age_hours=age_hours,
            relevance=relevance,
            reasoning=reasoning,
            breakdown=breakdown,
            is_current_focus=mission.id == current_id,
        )

    @staticmethod
    def _build_recommendation(
        ranked: tuple[MissionEvaluation, ...],
        current: Mission | None,
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> FocusRecommendation:
        if not ranked:
            base_reasoning = "No active missions to focus on."
            if reasoning_result is not None:
                base_reasoning = (
                    f"{reasoning_result.recommendation.strategy}. {base_reasoning}"
                )
            return FocusRecommendation(
                recommended_mission_id=None,
                recommended_title=None,
                current_mission_id=current.id if current is not None else None,
                should_switch=False,
                reasoning=base_reasoning,
                priority_score=0.0,
            )

        top = ranked[0]
        current_id = current.id if current is not None else None
        should_switch = bool(current_id and top.mission_id != current_id)

        if should_switch:
            reasoning = (
                f"Recommend switching focus from current mission to "
                f"« {top.title} » (score {top.priority_score:.1f}). {top.reasoning}"
            )
        elif current_id is None:
            reasoning = (
                f"Recommend focusing on « {top.title} » "
                f"(score {top.priority_score:.1f}). {top.reasoning}"
            )
        else:
            reasoning = (
                f"Keep focus on « {top.title} » "
                f"(score {top.priority_score:.1f}). {top.reasoning}"
            )

        if reasoning_result is not None:
            reasoning = (
                f"Reasoning Engine: {reasoning_result.recommendation.strategy}. "
                f"Mission focus: {reasoning}"
            )

        return FocusRecommendation(
            recommended_mission_id=top.mission_id,
            recommended_title=top.title,
            current_mission_id=current_id,
            should_switch=should_switch,
            reasoning=reasoning,
            priority_score=top.priority_score,
        )

    @staticmethod
    def _build_overall_reasoning(
        ranked: tuple[MissionEvaluation, ...],
        current: Mission | None,
        recommendation: FocusRecommendation,
        blocked: tuple[MissionEvaluation, ...],
        idle: tuple[MissionEvaluation, ...],
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> str:
        if reasoning_result is not None:
            parts: list[str] = [
                f"Reasoning Engine ({reasoning_result.summary.domain.value}): "
                f"{reasoning_result.recommendation.strategy} "
                f"(confidence {reasoning_result.summary.confidence_score:.2f}).",
            ]
            if reasoning_result.open_questions:
                parts.append(
                    f"Open questions: {len(reasoning_result.open_questions)} pending."
                )
        else:
            parts = []

        if not ranked:
            if parts:
                parts.append(
                    "No active missions. Executive Function has nothing to prioritize."
                )
                return " ".join(parts)
            return "No active missions. Executive Function has nothing to prioritize."

        parts.append(
            f"Evaluated {len(ranked)} active mission(s); "
            f"top candidate is « {recommendation.recommended_title} » "
            f"with priority score {recommendation.priority_score:.1f}."
        )
        if current is not None:
            parts.append(f"Current focus: « {current.title} » ({current.state.value}).")
        else:
            parts.append("No mission is currently marked as focus.")
        if blocked:
            titles = ", ".join(f"« {item.title} »" for item in blocked)
            parts.append(f"Blocked missions detected: {titles}.")
        if idle:
            titles = ", ".join(f"« {item.title} »" for item in idle)
            parts.append(f"Idle missions detected: {titles}.")
        if recommendation.should_switch:
            parts.append("Mission switch recommended before cognition continues.")
        else:
            parts.append("No mission switch required.")
        return " ".join(parts)


def _rank_key(evaluation: MissionEvaluation) -> tuple[float, float, float, str]:
    """Sort key: higher score first; ties broken by relevance, then age, then id."""
    return (
        -evaluation.priority_score,
        -evaluation.relevance,
        -evaluation.age_hours,
        evaluation.mission_id,
    )


def _progress_score(progress_percent: float) -> float:
    """Prefer missions with momentum; near-complete work gets a finish boost."""
    progress = max(0.0, min(100.0, progress_percent))
    if progress >= 80.0:
        return 12.0
    if progress >= 40.0:
        return 10.0
    if progress > 0.0:
        return 6.0
    return 3.0


def _relevance_score(
    mission: Mission,
    message: str,
    retrieval: RetrievalResult | None,
    workspace: WorkspaceSnapshot | None = None,
) -> float:
    """Score 0.0–1.0 from user message, retrieved memory, and workspace overlap."""
    corpus_parts = [
        mission.title,
        mission.objective,
        mission.current_step or "",
        " ".join(mission.steps),
        " ".join(mission.remaining_steps),
    ]
    if mission.goal is not None:
        corpus_parts.append(mission.goal.description)
    corpus = " ".join(corpus_parts).lower()
    corpus_tokens = set(_TOKEN_RE.findall(corpus))

    message_tokens = set(_TOKEN_RE.findall(message.lower()))
    if not message_tokens and retrieval is None and workspace is None:
        return 0.0

    overlap = message_tokens & corpus_tokens
    message_score = 0.0
    if message_tokens:
        message_score = len(overlap) / max(len(message_tokens), 1)

    memory_score = 0.0
    if retrieval is not None and retrieval.has_matches:
        memory_blob = " ".join(retrieval.items).lower()
        memory_tokens = set(_TOKEN_RE.findall(memory_blob))
        memory_overlap = memory_tokens & corpus_tokens
        if memory_tokens:
            memory_score = len(memory_overlap) / max(len(memory_tokens), 1)
        # Title/objective appearing in memory text is a strong signal.
        title = mission.title.lower().strip()
        if title and title in memory_blob:
            memory_score = max(memory_score, 0.7)

    workspace_score = 0.0
    if workspace is not None:
        workspace_blob = " ".join(
            [
                workspace.current_project,
                " ".join(workspace.detected_modules),
                " ".join(workspace.recently_modified_files[:12]),
                " ".join(workspace.documentation_files[:8]),
                " ".join(workspace.memory_hints),
            ]
        ).lower()
        workspace_tokens = set(_TOKEN_RE.findall(workspace_blob))
        workspace_overlap = workspace_tokens & corpus_tokens
        if workspace_tokens and workspace_overlap:
            workspace_score = len(workspace_overlap) / max(len(corpus_tokens), 1)
            workspace_score = min(1.0, workspace_score * 2.0)

    return min(1.0, message_score * 0.7 + memory_score * 0.5 + workspace_score * 0.35)


def _blocked_duration_hours(mission: Mission, now: datetime) -> float:
    """Hours since the mission entered BLOCKED (history or updated_at fallback)."""
    blocked_at: datetime | None = None
    for entry in reversed(mission.history):
        detail = (entry.detail or "").lower()
        event = entry.event.lower()
        if "blocked" in event or "blocked" in detail:
            blocked_at = entry.timestamp
            break
        # Tool failures transition missions to BLOCKED in Mission Runtime.
        if event == "tool_execution_failed":
            blocked_at = entry.timestamp
            break
        metadata = entry.metadata or {}
        state_value = str(metadata.get("state", metadata.get("new_state", ""))).upper()
        if state_value == MissionState.BLOCKED.value:
            blocked_at = entry.timestamp
            break
        changed = metadata.get("changed")
        if (
            isinstance(changed, list)
            and "state" in changed
            and mission.state == MissionState.BLOCKED
        ):
            blocked_at = entry.timestamp
            break
    if blocked_at is None:
        blocked_at = mission.updated_at
    return _hours_since(blocked_at, now)


def _mission_reasoning(
    mission: Mission,
    *,
    total: float,
    relevance: float,
    is_blocked: bool,
    is_idle: bool,
    blocked_hours: float,
    idle_hours: float,
    age_hours: float,
) -> str:
    parts = [
        f"Priority {mission.priority.value}, state {mission.state.value}, "
        f"progress {mission.progress_percent:.0f}%, score {total:.1f}."
    ]
    if is_blocked:
        parts.append(f"Blocked for {blocked_hours:.1f}h — needs attention.")
    if is_idle:
        parts.append(f"Idle for {idle_hours:.1f}h.")
    if relevance >= 0.35:
        parts.append(f"Strong relevance to current request ({relevance:.2f}).")
    elif relevance > 0.0:
        parts.append(f"Partial relevance to current request ({relevance:.2f}).")
    if age_hours >= 48:
        parts.append(f"Mission age {age_hours:.0f}h increases scheduling weight.")
    return " ".join(parts)


def _hours_since(moment: datetime, now: datetime) -> float:
    start = _ensure_aware(moment)
    end = _ensure_aware(now)
    delta = end - start
    return max(0.0, delta.total_seconds() / 3600.0)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

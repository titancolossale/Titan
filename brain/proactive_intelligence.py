# =====================================
# Titan Proactive Intelligence
# =====================================

"""Proactive Intelligence V1 — ranked recommendations from existing context.

Analyzes missions, workspace, development sessions, memory, and execution
state to surface what deserves attention. Suggests actions only; never
executes tools, mutates missions, or runs background schedulers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from brain.cognitive_loop import ThoughtPriority
from brain.development_session import DevelopmentSession

if TYPE_CHECKING:
    from brain.cognitive_loop import CognitiveLoopResult
    from brain.development_session import DevelopmentSessionRuntime
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.reasoning_engine import ReasoningEngine
    from brain.reasoning_models import ReasoningResult
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService
    from tools.confirmation_gate import ConfirmationGate

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_STORE_PATH = "data/proactive_intelligence.json"
MAX_RECOMMENDATIONS = 5
MIN_CONFIDENCE = 0.35
DEFAULT_COOLDOWN_HOURS = 24.0
SNOOZE_DEFAULT_HOURS = 4.0
BLOCKED_URGENCY_HOURS = 24.0
IDLE_URGENCY_HOURS = 48.0

_PRIORITY_RANK = {
    ThoughtPriority.CRITICAL: 0,
    ThoughtPriority.HIGH: 1,
    ThoughtPriority.NORMAL: 2,
    ThoughtPriority.LOW: 3,
}


class RecommendationCategory(str, Enum):
    """Classification of proactive recommendations."""

    MISSION_BLOCKED = "MISSION_BLOCKED"
    MISSION_IDLE = "MISSION_IDLE"
    MISSION_PRIORITY = "MISSION_PRIORITY"
    DEVELOPMENT_CONTINUATION = "DEVELOPMENT_CONTINUATION"
    PATCH_AWAITING_REVIEW = "PATCH_AWAITING_REVIEW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    WORKSPACE_CHANGE = "WORKSPACE_CHANGE"
    MISSING_DOCUMENTATION = "MISSING_DOCUMENTATION"
    FAILED_EXECUTION = "FAILED_EXECUTION"
    DEADLINE_RISK = "DEADLINE_RISK"
    QUICK_WIN = "QUICK_WIN"
    FOLLOW_UP = "FOLLOW_UP"
    REMINDER = "REMINDER"
    WELLBEING = "WELLBEING"
    GENERAL_OPPORTUNITY = "GENERAL_OPPORTUNITY"


class RecommendationStatus(str, Enum):
    """Lifecycle state for a surfaced recommendation."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ProactiveSignal:
    """Raw factual signal collected from an existing subsystem."""

    id: str
    source: str
    summary: str
    detail: str
    importance: float
    category_hint: RecommendationCategory | None
    fingerprint_seed: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "summary": self.summary,
            "detail": self.detail,
            "importance": round(self.importance, 3),
            "category_hint": (
                self.category_hint.value if self.category_hint is not None else None
            ),
            "fingerprint_seed": self.fingerprint_seed,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RecommendationReason:
    """User-safe concise rationale for a recommendation."""

    summary: str
    factors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "factors": list(self.factors),
        }


@dataclass(frozen=True)
class RecommendationAction:
    """Suggested next step — advisory only, never auto-executed."""

    label: str
    description: str
    requires_confirmation: bool = True
    required_tools: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "description": self.description,
            "requires_confirmation": self.requires_confirmation,
            "required_tools": list(self.required_tools),
        }


@dataclass(frozen=True)
class ProactiveRecommendation:
    """Ranked actionable suggestion for user attention."""

    id: str
    title: str
    summary: str
    category: RecommendationCategory
    priority: ThoughtPriority
    confidence: float
    source: str
    reason: RecommendationReason
    supporting_signals: tuple[ProactiveSignal, ...]
    recommended_action: RecommendationAction
    required_tools: tuple[str, ...]
    requires_confirmation: bool
    related_mission_id: str | None
    related_development_session_id: str | None
    created_at: datetime
    expires_at: datetime | None
    status: RecommendationStatus
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "category": self.category.value,
            "priority": self.priority.value,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "reason": self.reason.to_dict(),
            "supporting_signals": [s.to_dict() for s in self.supporting_signals],
            "recommended_action": self.recommended_action.to_dict(),
            "required_tools": list(self.required_tools),
            "requires_confirmation": self.requires_confirmation,
            "related_mission_id": self.related_mission_id,
            "related_development_session_id": self.related_development_session_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class AttentionItem:
    """Compact digest entry for dashboards and quick status."""

    recommendation_id: str
    title: str
    summary: str
    category: RecommendationCategory
    priority: ThoughtPriority
    confidence: float
    source: str
    related_mission_id: str | None
    related_development_session_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "summary": self.summary,
            "category": self.category.value,
            "priority": self.priority.value,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "related_mission_id": self.related_mission_id,
            "related_development_session_id": self.related_development_session_id,
        }


@dataclass(frozen=True)
class ProactiveDigest:
    """Ranked set of recommendations for one evaluation cycle."""

    generated_at: datetime
    recommendations: tuple[ProactiveRecommendation, ...]
    attention_items: tuple[AttentionItem, ...]
    signal_count: int
    suppressed_duplicates: int
    suppressed_lifecycle: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "attention_items": [a.to_dict() for a in self.attention_items],
            "signal_count": self.signal_count,
            "suppressed_duplicates": self.suppressed_duplicates,
            "suppressed_lifecycle": self.suppressed_lifecycle,
        }


@dataclass(frozen=True)
class ProactiveEvaluation:
    """Full result of one proactive context evaluation."""

    message: str
    digest: ProactiveDigest
    signals: tuple[ProactiveSignal, ...]
    duration_seconds: float
    reasoning_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "digest": self.digest.to_dict(),
            "signals": [s.to_dict() for s in self.signals],
            "duration_seconds": round(self.duration_seconds, 4),
            "reasoning_summary": self.reasoning_summary,
        }


@dataclass
class _LifecycleRecord:
    """Persisted user action on a recommendation fingerprint."""

    fingerprint: str
    recommendation_id: str
    status: RecommendationStatus
    updated_at: str
    snoozed_until: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "recommendation_id": self.recommendation_id,
            "status": self.status.value,
            "updated_at": self.updated_at,
            "snoozed_until": self.snoozed_until,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _LifecycleRecord:
        return cls(
            fingerprint=str(data["fingerprint"]),
            recommendation_id=str(data.get("recommendation_id") or ""),
            status=RecommendationStatus(data.get("status", RecommendationStatus.ACTIVE.value)),
            updated_at=str(data.get("updated_at") or _utc_now()),
            snoozed_until=data.get("snoozed_until"),
        )


class ProactiveIntelligence:
    """Collect signals, rank recommendations, manage lifecycle — read-only analysis."""

    def __init__(
        self,
        *,
        executive_function: ExecutiveFunction | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
        mission_manager: MissionManager | None = None,
        development_session: DevelopmentSessionRuntime | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
        reasoning_engine: ReasoningEngine | None = None,
        confirmation_gate: ConfirmationGate | None = None,
        file_path: str | Path = DEFAULT_STORE_PATH,
        max_recommendations: int = MAX_RECOMMENDATIONS,
        min_confidence: float = MIN_CONFIDENCE,
        cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
    ) -> None:
        self._executive_function = executive_function
        self._workspace_awareness = workspace_awareness
        self._mission_manager = mission_manager
        self._development_session = development_session
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._reasoning_engine = reasoning_engine
        self._confirmation_gate = confirmation_gate
        self._file_path = Path(file_path)
        self._max_recommendations = max_recommendations
        self._min_confidence = min_confidence
        self._cooldown_hours = cooldown_hours
        self._lifecycle: dict[str, _LifecycleRecord] = {}
        self._last_digest: ProactiveDigest | None = None
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        workspace: WorkspaceSnapshot | None = None,
        cognitive_result: CognitiveLoopResult | None = None,
        reasoning_result: ReasoningResult | None = None,
    ) -> ProactiveEvaluation:
        """Analyze existing context and produce a ranked proactive digest."""
        started = time.perf_counter()
        now = _utc_now_dt()
        resolved_user = user or self._resolve_user()
        resolved_project = project_id or self._resolve_project()

        logger.info(
            "Proactive evaluation start user=%s project=%s",
            resolved_user,
            resolved_project or "(none)",
        )

        workspace_snapshot = workspace
        if workspace_snapshot is None and self._workspace_awareness is not None:
            workspace_snapshot = self._workspace_awareness.refresh(
                user=resolved_user,
                project_id=resolved_project,
            )

        evaluation = executive_evaluation
        if evaluation is None and self._executive_function is not None:
            evaluation = self._executive_function.evaluate_missions(
                message,
                user=resolved_user,
                project_id=resolved_project,
                now=now,
                workspace=workspace_snapshot,
            )

        if reasoning_result is None and self._reasoning_engine is not None and message.strip():
            try:
                reasoning_result = self._reasoning_engine.reason(
                    message,
                    user=resolved_user,
                    project_id=resolved_project,
                    workspace=workspace_snapshot,
                )
            except Exception:
                logger.debug("Proactive reasoning enrichment failed", exc_info=True)

        signals = self._collect_signals(
            message=message,
            user=resolved_user,
            project_id=resolved_project,
            now=now,
            executive_evaluation=evaluation,
            workspace=workspace_snapshot,
            cognitive_result=cognitive_result,
            reasoning_result=reasoning_result,
        )

        candidates, suppressed_duplicates = self._signals_to_candidates(signals, now)
        ranked = self._rank_candidates(candidates)
        filtered, suppressed_lifecycle = self._apply_lifecycle_filters(ranked, now)
        capped = filtered[: self._max_recommendations]

        attention_items = tuple(
            AttentionItem(
                recommendation_id=rec.id,
                title=rec.title,
                summary=rec.summary,
                category=rec.category,
                priority=rec.priority,
                confidence=rec.confidence,
                source=rec.source,
                related_mission_id=rec.related_mission_id,
                related_development_session_id=rec.related_development_session_id,
            )
            for rec in capped
        )

        digest = ProactiveDigest(
            generated_at=now,
            recommendations=tuple(capped),
            attention_items=attention_items,
            signal_count=len(signals),
            suppressed_duplicates=suppressed_duplicates,
            suppressed_lifecycle=suppressed_lifecycle,
        )
        self._last_digest = digest

        reasoning_summary = None
        if reasoning_result is not None:
            summary = getattr(reasoning_result, "summary", None)
            if summary is not None:
                reasoning_summary = str(getattr(summary, "headline", "") or "")[:300] or None

        duration = time.perf_counter() - started
        logger.info(
            "Proactive evaluation done signals=%d recommendations=%d "
            "suppressed_dup=%d suppressed_lifecycle=%d duration=%.4fs",
            len(signals),
            len(capped),
            suppressed_duplicates,
            suppressed_lifecycle,
            duration,
        )

        return ProactiveEvaluation(
            message=message,
            digest=digest,
            signals=tuple(signals),
            duration_seconds=duration,
            reasoning_summary=reasoning_summary,
        )

    def get_digest(self) -> ProactiveDigest:
        """Return the most recent digest, or an empty one if none evaluated yet."""
        if self._last_digest is not None:
            return self._last_digest
        now = _utc_now_dt()
        return ProactiveDigest(
            generated_at=now,
            recommendations=(),
            attention_items=(),
            signal_count=0,
            suppressed_duplicates=0,
            suppressed_lifecycle=0,
        )

    def get_attention_items(self) -> tuple[AttentionItem, ...]:
        """Return attention items from the latest digest."""
        return self.get_digest().attention_items

    def acknowledge_recommendation(self, recommendation_id: str) -> bool:
        """Mark a recommendation as acknowledged."""
        return self._update_lifecycle(recommendation_id, RecommendationStatus.ACKNOWLEDGED)

    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        """Permanently suppress a recommendation fingerprint."""
        return self._update_lifecycle(recommendation_id, RecommendationStatus.DISMISSED)

    def snooze_recommendation(
        self,
        recommendation_id: str,
        until: datetime | None = None,
    ) -> bool:
        """Snooze a recommendation until *until* (default +4h)."""
        snooze_until = until or (_utc_now_dt() + timedelta(hours=SNOOZE_DEFAULT_HOURS))
        return self._update_lifecycle(
            recommendation_id,
            RecommendationStatus.SNOOZED,
            snoozed_until=snooze_until,
        )

    def complete_recommendation(self, recommendation_id: str) -> bool:
        """Mark a recommendation as completed by the user."""
        return self._update_lifecycle(recommendation_id, RecommendationStatus.COMPLETED)

    # ------------------------------------------------------------------
    # Signal collection
    # ------------------------------------------------------------------

    def _collect_signals(
        self,
        *,
        message: str,
        user: str,
        project_id: str | None,
        now: datetime,
        executive_evaluation: ExecutiveEvaluation | None,
        workspace: WorkspaceSnapshot | None,
        cognitive_result: CognitiveLoopResult | None,
        reasoning_result: ReasoningResult | None,
    ) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []

        if executive_evaluation is not None:
            signals.extend(self._signals_from_executive(executive_evaluation, now))
        if workspace is not None:
            signals.extend(self._signals_from_workspace(workspace, now))
        signals.extend(self._signals_from_development_session(now))
        signals.extend(self._signals_from_approvals(now))
        if cognitive_result is not None:
            signals.extend(self._signals_from_cognitive(cognitive_result, now))
        if reasoning_result is not None:
            signals.extend(self._signals_from_reasoning(reasoning_result, now))
        signals.extend(self._signals_from_memory(message, user, project_id, now))

        return signals

    def _signals_from_executive(
        self,
        evaluation: ExecutiveEvaluation,
        now: datetime,
    ) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []

        for blocked in evaluation.blocked_missions:
            importance = min(0.98, 0.6 + blocked.blocked_hours / 72.0)
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="executive_function",
                    summary=f"Mission « {blocked.title} » is blocked.",
                    detail=blocked.reasoning,
                    importance=importance,
                    category_hint=RecommendationCategory.MISSION_BLOCKED,
                    fingerprint_seed=f"mission_blocked:{blocked.mission_id}",
                    timestamp=now,
                    metadata={
                        "mission_id": blocked.mission_id,
                        "blocked_hours": blocked.blocked_hours,
                        "priority": blocked.priority.value,
                    },
                )
            )

        for idle in evaluation.idle_missions:
            if idle.age_hours < IDLE_URGENCY_HOURS:
                continue
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="executive_function",
                    summary=f"Mission « {idle.title} » has been idle.",
                    detail=idle.reasoning,
                    importance=min(0.75, 0.4 + idle.age_hours / 168.0),
                    category_hint=RecommendationCategory.MISSION_IDLE,
                    fingerprint_seed=f"mission_idle:{idle.mission_id}",
                    timestamp=now,
                    metadata={
                        "mission_id": idle.mission_id,
                        "age_hours": idle.age_hours,
                    },
                )
            )

        recommended = evaluation.recommended_next_mission
        if recommended is not None and evaluation.recommendation.should_switch:
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="executive_function",
                    summary=(
                        f"Executive focus recommends « {recommended.title} »."
                    ),
                    detail=evaluation.recommendation.reasoning,
                    importance=0.72,
                    category_hint=RecommendationCategory.MISSION_PRIORITY,
                    fingerprint_seed=f"mission_priority:{recommended.mission_id}",
                    timestamp=now,
                    metadata={"mission_id": recommended.mission_id},
                )
            )

        return signals

    def _signals_from_workspace(
        self,
        workspace: WorkspaceSnapshot,
        now: datetime,
    ) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []
        for rec in workspace.recommendations or ():
            kind = str(getattr(rec, "kind", "") or "")
            summary = str(getattr(rec, "summary", "") or "")
            detail = str(getattr(rec, "detail", "") or "")
            paths = tuple(getattr(rec, "related_paths", ()) or ())
            category = RecommendationCategory.WORKSPACE_CHANGE
            if kind == "missing_documentation":
                category = RecommendationCategory.MISSING_DOCUMENTATION
            elif kind == "documentation_changed":
                category = RecommendationCategory.WORKSPACE_CHANGE
            elif kind == "new_modules":
                category = RecommendationCategory.WORKSPACE_CHANGE
            elif kind == "large_unfinished_feature":
                category = RecommendationCategory.GENERAL_OPPORTUNITY

            seed = f"workspace:{kind}:{summary[:80]}"
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="workspace_awareness",
                    summary=summary,
                    detail=detail,
                    importance=0.55 if category == RecommendationCategory.MISSING_DOCUMENTATION else 0.45,
                    category_hint=category,
                    fingerprint_seed=seed,
                    timestamp=now,
                    metadata={"kind": kind, "paths": list(paths)},
                )
            )
        return signals

    def _signals_from_development_session(self, now: datetime) -> list[ProactiveSignal]:
        if self._development_session is None:
            return []

        signals: list[ProactiveSignal] = []
        sessions = list(getattr(self._development_session, "_sessions", {}).values())
        for session in sessions:
            if not isinstance(session, DevelopmentSession):
                continue
            if session.state.value == "paused" and session.pending_tasks:
                count = len(session.pending_tasks)
                signals.append(
                    ProactiveSignal(
                        id=_new_id(),
                        source="development_session",
                        summary=(
                            f"Resume « {session.feature} » session — "
                            f"{count} task(s) remain."
                        ),
                        detail="; ".join(t.description for t in session.pending_tasks[:5]),
                        importance=min(0.9, 0.55 + count * 0.05),
                        category_hint=RecommendationCategory.DEVELOPMENT_CONTINUATION,
                        fingerprint_seed=f"dev_session:{session.session_id}:paused",
                        timestamp=now,
                        metadata={
                            "session_id": session.session_id,
                            "pending_count": count,
                        },
                    )
                )

            pending_patches = [
                p for p in (session.patches or [])
                if not p.get("_applied", False) and not p.get("approved", False)
            ]
            if pending_patches:
                signals.append(
                    ProactiveSignal(
                        id=_new_id(),
                        source="development_session",
                        summary="Review the pending patch before continuing implementation.",
                        detail=f"{len(pending_patches)} unreviewed patch(es) in session.",
                        importance=0.78,
                        category_hint=RecommendationCategory.PATCH_AWAITING_REVIEW,
                        fingerprint_seed=f"patch_review:{session.session_id}",
                        timestamp=now,
                        metadata={"session_id": session.session_id},
                    )
                )

            stale_plans = [
                p for p in (session.plans or [])
                if p.get("status") in (None, "draft", "pending")
            ]
            if stale_plans and session.state.value != "ended":
                signals.append(
                    ProactiveSignal(
                        id=_new_id(),
                        source="development_session",
                        summary=f"Unfinished plan in « {session.feature} » session.",
                        detail=f"{len(stale_plans)} plan(s) not completed.",
                        importance=0.42,
                        category_hint=RecommendationCategory.FOLLOW_UP,
                        fingerprint_seed=f"stale_plan:{session.session_id}",
                        timestamp=now,
                        metadata={"session_id": session.session_id},
                    )
                )
        return signals

    def _signals_from_approvals(self, now: datetime) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []
        gate = self._confirmation_gate
        if gate is None:
            return signals

        pending_store = getattr(gate, "_pending", None)
        if not isinstance(pending_store, dict) or not pending_store:
            return signals

        count = len(pending_store)
        signals.append(
            ProactiveSignal(
                id=_new_id(),
                source="confirmation_gate",
                summary=f"{count} tool action(s) await your approval.",
                detail="Confirm or dismiss pending tool requests before retrying.",
                importance=0.82,
                category_hint=RecommendationCategory.APPROVAL_REQUIRED,
                fingerprint_seed="approval:tool_pending",
                timestamp=now,
                metadata={"pending_count": count},
            )
        )
        return signals

    def _signals_from_cognitive(
        self,
        result: CognitiveLoopResult,
        now: datetime,
    ) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []
        for rec in result.recommendations:
            if rec.confidence < self._min_confidence:
                continue
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="cognitive_loop",
                    summary=rec.summary,
                    detail=rec.action,
                    importance=min(0.85, rec.confidence),
                    category_hint=RecommendationCategory.GENERAL_OPPORTUNITY,
                    fingerprint_seed=f"cognitive:{rec.id}",
                    timestamp=now,
                    metadata={"thought_id": rec.thought_id},
                )
            )
        return signals

    def _signals_from_reasoning(
        self,
        result: ReasoningResult,
        now: datetime,
    ) -> list[ProactiveSignal]:
        signals: list[ProactiveSignal] = []
        summary = getattr(result, "summary", None)
        recommendation = getattr(result, "recommendation", None)
        if summary is None:
            return signals

        confidence = float(getattr(summary, "confidence_score", 0.0) or 0.0)
        if confidence < self._min_confidence:
            return signals

        if getattr(summary, "clarification_required", False):
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="reasoning_engine",
                    summary="Clarification may help before proceeding.",
                    detail=str(getattr(summary, "headline", "") or "")[:200],
                    importance=0.5,
                    category_hint=RecommendationCategory.FOLLOW_UP,
                    fingerprint_seed="reasoning:clarification",
                    timestamp=now,
                )
            )

        risks = getattr(result, "risks", ()) or ()
        for risk in risks[:2]:
            label = str(getattr(risk, "label", "") or getattr(risk, "description", ""))
            if not label:
                continue
            signals.append(
                ProactiveSignal(
                    id=_new_id(),
                    source="reasoning_engine",
                    summary=f"Risk: {label[:120]}",
                    detail=str(getattr(risk, "mitigation", "") or "")[:200],
                    importance=0.6,
                    category_hint=RecommendationCategory.DEADLINE_RISK,
                    fingerprint_seed=f"reasoning:risk:{label[:40]}",
                    timestamp=now,
                )
            )

        if recommendation is not None:
            strategy = str(getattr(recommendation, "strategy", "") or "")
            if strategy and confidence >= 0.5:
                signals.append(
                    ProactiveSignal(
                        id=_new_id(),
                        source="reasoning_engine",
                        summary=strategy[:160],
                        detail=str(getattr(recommendation, "rationale", "") or "")[:200],
                        importance=confidence * 0.7,
                        category_hint=RecommendationCategory.QUICK_WIN,
                        fingerprint_seed=f"reasoning:strategy:{strategy[:40]}",
                        timestamp=now,
                    )
                )
        return signals

    def _signals_from_memory(
        self,
        message: str,
        user: str,
        project_id: str | None,
        now: datetime,
    ) -> list[ProactiveSignal]:
        if self._memory_service is None:
            return []

        signals: list[ProactiveSignal] = []
        retrieval = self._memory_service.retrieve(user, message or "priorities", project_id=project_id)
        if not retrieval.has_matches:
            return signals

        priority_keywords = ("priority", "priorité", "urgent", "focus", "goal", "objectif")
        for item in retrieval.items[:3]:
            text = f"{getattr(item, 'content', '')} {getattr(item, 'category', '')}".lower()
            if any(kw in text for kw in priority_keywords):
                content = str(getattr(item, "content", "") or "")[:160]
                signals.append(
                    ProactiveSignal(
                        id=_new_id(),
                        source="memory",
                        summary=f"Recent priority noted: {content}",
                        detail="Matches stored user priority or goal.",
                        importance=0.48,
                        category_hint=RecommendationCategory.REMINDER,
                        fingerprint_seed=f"memory:priority:{hashlib.sha256(content.encode()).hexdigest()[:12]}",
                        timestamp=now,
                    )
                )
        return signals

    # ------------------------------------------------------------------
    # Ranking and lifecycle
    # ------------------------------------------------------------------

    def _signals_to_candidates(
        self,
        signals: list[ProactiveSignal],
        now: datetime,
    ) -> tuple[list[ProactiveRecommendation], int]:
        candidates: list[ProactiveRecommendation] = []
        seen_fingerprints: set[str] = set()
        suppressed = 0

        for signal in signals:
            fingerprint = _fingerprint(signal.fingerprint_seed)
            if fingerprint in seen_fingerprints:
                suppressed += 1
                continue
            seen_fingerprints.add(fingerprint)

            category = signal.category_hint or RecommendationCategory.GENERAL_OPPORTUNITY
            priority = _category_priority(category, signal)
            confidence = _compute_confidence(signal, priority)
            if confidence < self._min_confidence:
                continue

            mission_id = signal.metadata.get("mission_id")
            session_id = signal.metadata.get("session_id")
            expires_at = None
            if category == RecommendationCategory.MISSION_BLOCKED:
                blocked_hours = float(signal.metadata.get("blocked_hours", 0))
                if blocked_hours >= BLOCKED_URGENCY_HOURS:
                    priority = ThoughtPriority.CRITICAL
                expires_at = now + timedelta(hours=72)

            action_label = _default_action_label(category)
            rec = ProactiveRecommendation(
                id=_new_id(),
                title=_title_for_signal(signal, category),
                summary=signal.summary,
                category=category,
                priority=priority,
                confidence=confidence,
                source=signal.source,
                reason=RecommendationReason(
                    summary=signal.detail or signal.summary,
                    factors=_reason_factors(signal, category),
                ),
                supporting_signals=(signal,),
                recommended_action=RecommendationAction(
                    label=action_label,
                    description=signal.summary,
                    requires_confirmation=True,
                    required_tools=_tools_for_category(category),
                ),
                required_tools=_tools_for_category(category),
                requires_confirmation=True,
                related_mission_id=str(mission_id) if mission_id else None,
                related_development_session_id=str(session_id) if session_id else None,
                created_at=now,
                expires_at=expires_at,
                status=RecommendationStatus.ACTIVE,
                fingerprint=fingerprint,
            )
            candidates.append(rec)

        return candidates, suppressed

    def _rank_candidates(
        self,
        candidates: list[ProactiveRecommendation],
    ) -> list[ProactiveRecommendation]:
        def sort_key(rec: ProactiveRecommendation) -> tuple[float, float, float]:
            priority_rank = _PRIORITY_RANK.get(rec.priority, 9)
            return (priority_rank, -rec.confidence, -_category_weight(rec.category))

        return sorted(candidates, key=sort_key)

    def _apply_lifecycle_filters(
        self,
        candidates: list[ProactiveRecommendation],
        now: datetime,
    ) -> tuple[list[ProactiveRecommendation], int]:
        filtered: list[ProactiveRecommendation] = []
        suppressed = 0

        for rec in candidates:
            if rec.expires_at is not None and now > rec.expires_at:
                suppressed += 1
                continue

            record = self._lifecycle.get(rec.fingerprint)
            if record is None:
                filtered.append(rec)
                continue

            if record.status == RecommendationStatus.DISMISSED:
                suppressed += 1
                logger.debug("Proactive suppressed dismissed fingerprint=%s", rec.fingerprint)
                continue

            if record.status == RecommendationStatus.COMPLETED:
                suppressed += 1
                continue

            if record.status == RecommendationStatus.SNOOZED and record.snoozed_until:
                snooze_end = _parse_dt(record.snoozed_until)
                if snooze_end is not None and now < snooze_end:
                    suppressed += 1
                    logger.debug("Proactive suppressed snoozed fingerprint=%s", rec.fingerprint)
                    continue

            if record.status == RecommendationStatus.ACKNOWLEDGED:
                ack_time = _parse_dt(record.updated_at)
                if ack_time is not None:
                    hours = (now - ack_time).total_seconds() / 3600.0
                    if hours < self._cooldown_hours:
                        suppressed += 1
                        continue

            filtered.append(rec)

        return filtered, suppressed

    def _update_lifecycle(
        self,
        recommendation_id: str,
        status: RecommendationStatus,
        *,
        snoozed_until: datetime | None = None,
    ) -> bool:
        rec = self._find_recommendation(recommendation_id)
        if rec is None:
            return False

        record = _LifecycleRecord(
            fingerprint=rec.fingerprint,
            recommendation_id=recommendation_id,
            status=status,
            updated_at=_utc_now(),
            snoozed_until=snoozed_until.isoformat() if snoozed_until else None,
        )
        self._lifecycle[rec.fingerprint] = record
        self._save()
        logger.info(
            "Proactive lifecycle %s fingerprint=%s recommendation=%s",
            status.value,
            rec.fingerprint,
            recommendation_id,
        )
        return True

    def _find_recommendation(self, recommendation_id: str) -> ProactiveRecommendation | None:
        digest = self.get_digest()
        for rec in digest.recommendations:
            if rec.id == recommendation_id:
                return rec
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file_path.exists():
            self._lifecycle = {}
            return
        try:
            with self._file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            logger.warning("Proactive store corrupt — starting fresh: %s", self._file_path)
            self._lifecycle = {}
            return

        records = data.get("lifecycle", {})
        self._lifecycle = {
            key: _LifecycleRecord.from_dict(value)
            for key, value in records.items()
            if isinstance(value, dict)
        }

    def _save(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "lifecycle": {
                key: record.to_dict() for key, record in self._lifecycle.items()
            },
        }
        with self._file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)

    def _resolve_user(self) -> str:
        if self._context_manager is not None:
            return getattr(self._context_manager, "current_user", None) or "Nolan"
        return "Nolan"

    def _resolve_project(self) -> str | None:
        if self._context_manager is not None:
            project = getattr(self._context_manager, "active_project", None)
            return project or None
        return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _category_priority(
    category: RecommendationCategory,
    signal: ProactiveSignal,
) -> ThoughtPriority:
    mapping = {
        RecommendationCategory.MISSION_BLOCKED: ThoughtPriority.CRITICAL,
        RecommendationCategory.APPROVAL_REQUIRED: ThoughtPriority.HIGH,
        RecommendationCategory.FAILED_EXECUTION: ThoughtPriority.HIGH,
        RecommendationCategory.PATCH_AWAITING_REVIEW: ThoughtPriority.HIGH,
        RecommendationCategory.DEADLINE_RISK: ThoughtPriority.HIGH,
        RecommendationCategory.MISSION_PRIORITY: ThoughtPriority.HIGH,
        RecommendationCategory.DEVELOPMENT_CONTINUATION: ThoughtPriority.NORMAL,
        RecommendationCategory.MISSION_IDLE: ThoughtPriority.NORMAL,
        RecommendationCategory.WORKSPACE_CHANGE: ThoughtPriority.NORMAL,
        RecommendationCategory.MISSING_DOCUMENTATION: ThoughtPriority.LOW,
        RecommendationCategory.QUICK_WIN: ThoughtPriority.NORMAL,
        RecommendationCategory.FOLLOW_UP: ThoughtPriority.LOW,
        RecommendationCategory.REMINDER: ThoughtPriority.LOW,
        RecommendationCategory.WELLBEING: ThoughtPriority.LOW,
        RecommendationCategory.GENERAL_OPPORTUNITY: ThoughtPriority.LOW,
    }
    base = mapping.get(category, ThoughtPriority.NORMAL)
    if signal.importance >= 0.85 and base.value != ThoughtPriority.CRITICAL.value:
        return ThoughtPriority.HIGH
    return base


def _compute_confidence(
    signal: ProactiveSignal,
    priority: ThoughtPriority,
) -> float:
    base = signal.importance
    if priority == ThoughtPriority.CRITICAL:
        base = min(0.98, base + 0.1)
    elif priority == ThoughtPriority.HIGH:
        base = min(0.95, base + 0.05)
    return round(base, 3)


def _category_weight(category: RecommendationCategory) -> float:
    weights = {
        RecommendationCategory.MISSION_BLOCKED: 100,
        RecommendationCategory.APPROVAL_REQUIRED: 90,
        RecommendationCategory.FAILED_EXECUTION: 85,
        RecommendationCategory.PATCH_AWAITING_REVIEW: 80,
        RecommendationCategory.MISSION_PRIORITY: 75,
        RecommendationCategory.DEVELOPMENT_CONTINUATION: 70,
        RecommendationCategory.DEADLINE_RISK: 65,
        RecommendationCategory.MISSION_IDLE: 50,
        RecommendationCategory.QUICK_WIN: 45,
        RecommendationCategory.WORKSPACE_CHANGE: 40,
        RecommendationCategory.FOLLOW_UP: 30,
        RecommendationCategory.REMINDER: 25,
        RecommendationCategory.MISSING_DOCUMENTATION: 20,
        RecommendationCategory.WELLBEING: 15,
        RecommendationCategory.GENERAL_OPPORTUNITY: 10,
    }
    return weights.get(category, 5)


def _title_for_signal(
    signal: ProactiveSignal,
    category: RecommendationCategory,
) -> str:
    titles = {
        RecommendationCategory.MISSION_BLOCKED: "Blocked mission needs review",
        RecommendationCategory.MISSION_IDLE: "Idle mission waiting",
        RecommendationCategory.MISSION_PRIORITY: "Mission focus recommendation",
        RecommendationCategory.DEVELOPMENT_CONTINUATION: "Resume development session",
        RecommendationCategory.PATCH_AWAITING_REVIEW: "Patch awaiting review",
        RecommendationCategory.APPROVAL_REQUIRED: "Approval required",
        RecommendationCategory.WORKSPACE_CHANGE: "Workspace change detected",
        RecommendationCategory.MISSING_DOCUMENTATION: "Documentation gap",
        RecommendationCategory.FAILED_EXECUTION: "Recent execution failure",
        RecommendationCategory.DEADLINE_RISK: "Deadline or risk signal",
        RecommendationCategory.QUICK_WIN: "Quick win available",
        RecommendationCategory.FOLLOW_UP: "Follow-up suggested",
        RecommendationCategory.REMINDER: "Reminder",
        RecommendationCategory.WELLBEING: "Wellbeing check",
        RecommendationCategory.GENERAL_OPPORTUNITY: "Opportunity",
    }
    return titles.get(category, signal.summary[:80])


def _default_action_label(category: RecommendationCategory) -> str:
    labels = {
        RecommendationCategory.MISSION_BLOCKED: "Review blocker",
        RecommendationCategory.MISSION_IDLE: "Resume or pause mission",
        RecommendationCategory.MISSION_PRIORITY: "Switch focus",
        RecommendationCategory.DEVELOPMENT_CONTINUATION: "Resume session",
        RecommendationCategory.PATCH_AWAITING_REVIEW: "Review patch",
        RecommendationCategory.APPROVAL_REQUIRED: "Review approval",
        RecommendationCategory.WORKSPACE_CHANGE: "Review workspace",
        RecommendationCategory.MISSING_DOCUMENTATION: "Update documentation",
        RecommendationCategory.FAILED_EXECUTION: "Inspect failure",
        RecommendationCategory.DEADLINE_RISK: "Address risk",
        RecommendationCategory.QUICK_WIN: "Take quick action",
        RecommendationCategory.FOLLOW_UP: "Follow up",
        RecommendationCategory.REMINDER: "Acknowledge reminder",
        RecommendationCategory.WELLBEING: "Take a break",
        RecommendationCategory.GENERAL_OPPORTUNITY: "Consider opportunity",
    }
    return labels.get(category, "Review")


def _tools_for_category(category: RecommendationCategory) -> tuple[str, ...]:
    if category == RecommendationCategory.PATCH_AWAITING_REVIEW:
        return ("code_editor",)
    if category in (
        RecommendationCategory.FAILED_EXECUTION,
        RecommendationCategory.APPROVAL_REQUIRED,
    ):
        return ("terminal",)
    return ()


def _reason_factors(
    signal: ProactiveSignal,
    category: RecommendationCategory,
) -> tuple[str, ...]:
    factors = [f"source={signal.source}", f"category={category.value}"]
    if "blocked_hours" in signal.metadata:
        factors.append(f"blocked_hours={signal.metadata['blocked_hours']}")
    if "age_hours" in signal.metadata:
        factors.append(f"age_hours={signal.metadata['age_hours']}")
    if "pending_count" in signal.metadata:
        factors.append(f"pending_count={signal.metadata['pending_count']}")
    return tuple(factors)

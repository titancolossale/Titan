# =====================================
# Titan Decision Engine
# =====================================

"""Select the next action among plan candidates (Phase 17.3–17.4).

Reuses PlanningEngine ``Plan``, Goal / Project / Mission entities, and
request-scoped WorkspaceState. Does not recreate those systems.

Scoring is a single evaluation pass — each candidate is scored once;
the highest overall score wins.

Phase 17.4 — learn from execution feedback: a single ``record_feedback``
update adjusts rolling history and future confidence (no duplicated
history rebuild).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain.decision_models import (
    ActionCandidateScore,
    Decision,
    DecisionFeedback,
    DecisionHistoryStats,
    compute_confidence,
    compute_feedback_score,
    compute_overall_score,
)
from brain.planning_models import Plan, PlanStatus, priority_weight
from config.settings import TITAN_DECISION_HISTORY_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_HISTORY_LIMIT = 50
LEARNING_RATE = 0.15
MAX_CONFIDENCE_BIAS = 0.30
BASE_LEARNING_CONFIDENCE = 0.5


class DecisionEngine:
    """Decide which plan action should execute next; learn from outcomes."""

    def __init__(
        self,
        *,
        history_path: str | Path | None = None,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        persist: bool = True,
    ) -> None:
        self._active_decision: Decision | None = None
        self._history: list[DecisionFeedback] = []
        self._history_limit = max(1, int(history_limit))
        self._confidence_bias = 0.0
        # Incremental aggregates — updated once per feedback (no full rebuild).
        self._success_count = 0
        self._feedback_sum = 0.0
        self._duration_sum = 0.0
        self._persist = persist
        self.file_path = (
            Path(history_path)
            if history_path is not None
            else Path(TITAN_DECISION_HISTORY_PATH)
        )
        if self._persist:
            self._load()

    @property
    def active_decision(self) -> Decision | None:
        return self._active_decision

    @property
    def history(self) -> list[DecisionFeedback]:
        """Rolling decision feedback history (most recent last)."""
        return list(self._history)

    @property
    def confidence_bias(self) -> float:
        """Additive confidence adjustment learned from feedback."""
        return self._confidence_bias

    @property
    def learning_confidence(self) -> float:
        """Current confidence from learning (0.0–1.0)."""
        return max(
            0.0,
            min(1.0, round(BASE_LEARNING_CONFIDENCE + self._confidence_bias, 4)),
        )

    @property
    def success_rate(self) -> float:
        return self.history_stats.success_rate

    @property
    def average_feedback(self) -> float:
        return self.history_stats.average_feedback

    @property
    def average_duration(self) -> float:
        return self.history_stats.average_duration

    @property
    def history_stats(self) -> DecisionHistoryStats:
        """Expose success_rate / average_feedback / average_duration."""
        count = len(self._history)
        if count <= 0:
            return DecisionHistoryStats(
                success_rate=0.0,
                average_feedback=0.0,
                average_duration=0.0,
                sample_count=0,
            )
        return DecisionHistoryStats(
            success_rate=round(self._success_count / count, 4),
            average_feedback=round(self._feedback_sum / count, 4),
            average_duration=round(self._duration_sum / count, 4),
            sample_count=count,
        )

    def decide(
        self,
        *,
        plan: Plan | None = None,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        now: datetime | None = None,
    ) -> Decision:
        """Score plan actions once and select the highest overall score.

        Args:
            plan: Current next-action Plan from PlanningEngine.
            workspace: Request-scoped WorkspaceState (already loaded).
            goal: Optional active Goal entity.
            project: Optional active Project entity.
            mission: Optional active Mission entity.
            now: Optional clock override for tests.

        Returns:
            A ``Decision`` with selected_action and factor scores.
        """
        stamp = now or datetime.now(timezone.utc)
        previous = self._active_decision

        if plan is None or not plan.next_actions:
            decision = Decision.empty(
                now=stamp,
                reason=self._empty_reason(plan),
            )
            if previous is not None and previous.created_at is not None:
                decision = Decision(
                    decision_id=previous.decision_id,
                    selected_action=decision.selected_action,
                    reason=decision.reason,
                    confidence=decision.confidence,
                    priority=decision.priority,
                    risk_score=decision.risk_score,
                    expected_value=decision.expected_value,
                    created_at=previous.created_at,
                    updated_at=stamp,
                    candidates=[],
                )
            decision = self._attach_learning_context(decision)
            self._active_decision = decision
            self._emit_diagnostics(decision, previous)
            return decision

        base_priority = self._base_priority(plan, goal, project, mission, workspace)
        base_urgency = self._base_urgency(plan, goal, project, mission, workspace)
        base_risk = self._base_risk(plan)
        unmet_deps = self._unmet_dependency_hint(plan)

        # Single evaluation pass — score every candidate exactly once.
        scored: list[ActionCandidateScore] = []
        actions = list(plan.next_actions)
        total = len(actions)
        for index, action in enumerate(actions):
            priority = self._action_priority(base_priority, index, total)
            urgency = base_urgency
            risk = self._action_risk(base_risk, index, total, unmet_deps)
            dependency = self._action_dependency(index, total, unmet_deps, plan)
            estimated_value = self._action_estimated_value(
                plan,
                index,
                total,
                base_priority,
            )
            overall = compute_overall_score(
                priority=priority,
                urgency=urgency,
                risk=risk,
                dependency=dependency,
                estimated_value=estimated_value,
            )
            scored.append(
                ActionCandidateScore(
                    action=action,
                    priority=round(priority, 4),
                    urgency=round(urgency, 4),
                    risk=round(risk, 4),
                    dependency=round(dependency, 4),
                    estimated_value=round(estimated_value, 4),
                    overall_score=overall,
                )
            )

        ranked = sorted(scored, key=lambda c: c.overall_score, reverse=True)
        winner = ranked[0]
        second = ranked[1].overall_score if len(ranked) > 1 else None
        base_confidence = compute_confidence(
            top_score=winner.overall_score,
            second_score=second,
            candidate_count=len(ranked),
        )
        # Phase 17.4 — apply learned bias to future scoring confidence.
        confidence = self._apply_confidence_bias(base_confidence)
        reason = self._build_reason(winner, plan, unmet_deps)

        created_at = previous.created_at if previous is not None else stamp
        decision_id = (
            previous.decision_id
            if previous is not None and previous.selected_action == winner.action
            else str(uuid.uuid4())
        )
        decision = Decision(
            decision_id=decision_id,
            selected_action=winner.action,
            reason=reason,
            confidence=confidence,
            priority=winner.priority,
            risk_score=winner.risk,
            expected_value=winner.estimated_value,
            created_at=created_at,
            updated_at=stamp,
            candidates=ranked,
        )
        decision = self._attach_learning_context(decision)
        self._active_decision = decision
        self._emit_diagnostics(decision, previous)
        return decision

    def record_feedback(
        self,
        *,
        actual_result: float,
        success: bool,
        duration: float = 0.0,
        decision_id: str | None = None,
        selected_action: str | None = None,
        expected_value: float | None = None,
        now: datetime | None = None,
    ) -> DecisionFeedback:
        """Record one execution outcome and update learning (single pass).

        Compares ``expected_value`` vs ``actual_result``, appends one history
        entry, updates rolling aggregates in O(1), and adjusts confidence bias.
        Does not rebuild history from scratch.

        Args:
            actual_result: Observed outcome score (0.0–1.0).
            success: Whether the executed action succeeded.
            duration: Execution duration in seconds.
            decision_id: Optional override; defaults to active decision.
            selected_action: Optional override; defaults to active decision.
            expected_value: Optional override; defaults to active decision.
            now: Optional clock override for tests.

        Returns:
            The recorded ``DecisionFeedback`` entry.
        """
        stamp = now or datetime.now(timezone.utc)
        active = self._active_decision
        resolved_id = decision_id or (
            active.decision_id if active is not None else str(uuid.uuid4())
        )
        resolved_action = selected_action or (
            active.selected_action if active is not None else None
        )
        if not resolved_action:
            resolved_action = "unknown"
        resolved_expected = (
            float(expected_value)
            if expected_value is not None
            else float(active.expected_value if active is not None else 0.0)
        )
        resolved_actual = max(0.0, min(1.0, float(actual_result)))
        resolved_duration = max(0.0, float(duration))
        feedback_score = compute_feedback_score(
            expected_value=resolved_expected,
            actual_result=resolved_actual,
            success=success,
        )

        entry = DecisionFeedback(
            decision_id=resolved_id,
            selected_action=resolved_action,
            expected_value=round(resolved_expected, 4),
            actual_result=round(resolved_actual, 4),
            success=bool(success),
            duration=round(resolved_duration, 4),
            feedback_score=feedback_score,
            completed_at=stamp,
        )

        previous_bias = self._confidence_bias
        self._append_feedback(entry)
        self._update_confidence_bias(feedback_score)

        logger.info(
            "DECISION_FEEDBACK decision_id=%s action=%s success=%s "
            "expected=%s actual=%s feedback_score=%s duration=%s",
            entry.decision_id,
            entry.selected_action,
            entry.success,
            entry.expected_value,
            entry.actual_result,
            entry.feedback_score,
            entry.duration,
        )
        stats = self.history_stats
        logger.info(
            "DECISION_HISTORY_UPDATED count=%s success_rate=%s "
            "average_feedback=%s average_duration=%s",
            stats.sample_count,
            stats.success_rate,
            stats.average_feedback,
            stats.average_duration,
        )
        if self._confidence_bias != previous_bias:
            logger.info(
                "DECISION_CONFIDENCE_UPDATED bias=%s learning_confidence=%s "
                "previous_bias=%s feedback_score=%s",
                self._confidence_bias,
                self.learning_confidence,
                previous_bias,
                feedback_score,
            )

        if self._active_decision is not None:
            self._active_decision = self._attach_learning_context(self._active_decision)

        if self._persist:
            self._save()
        return entry

    def _append_feedback(self, entry: DecisionFeedback) -> None:
        """Append one feedback entry; trim oldest with incremental aggregate fix."""
        if len(self._history) >= self._history_limit:
            oldest = self._history.pop(0)
            self._success_count = max(0, self._success_count - int(oldest.success))
            self._feedback_sum -= oldest.feedback_score
            self._duration_sum -= oldest.duration
        self._history.append(entry)
        self._success_count += int(entry.success)
        self._feedback_sum += entry.feedback_score
        self._duration_sum += entry.duration

    def _update_confidence_bias(self, feedback_score: float) -> None:
        delta = LEARNING_RATE * float(feedback_score)
        self._confidence_bias = max(
            -MAX_CONFIDENCE_BIAS,
            min(MAX_CONFIDENCE_BIAS, round(self._confidence_bias + delta, 4)),
        )

    def _apply_confidence_bias(self, base_confidence: float) -> float:
        return max(
            0.0,
            min(1.0, round(float(base_confidence) + self._confidence_bias, 4)),
        )

    def _attach_learning_context(self, decision: Decision) -> Decision:
        """Attach rolling history stats for PromptBuilder (no history rebuild)."""
        stats = self.history_stats
        decision.success_rate = stats.success_rate
        decision.average_feedback = stats.average_feedback
        decision.average_duration = stats.average_duration
        decision.learning_confidence = self.learning_confidence
        # Share a shallow snapshot of recent entries (already in memory).
        decision.recent_history = list(self._history[-5:])
        return decision

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Decision history load failed path=%s error=%s",
                self.file_path,
                exc,
            )
            return
        if not isinstance(data, dict):
            return
        self._confidence_bias = max(
            -MAX_CONFIDENCE_BIAS,
            min(MAX_CONFIDENCE_BIAS, float(data.get("confidence_bias") or 0.0)),
        )
        raw_history = data.get("history") or []
        loaded: list[DecisionFeedback] = []
        if isinstance(raw_history, list):
            for item in raw_history[-self._history_limit :]:
                if isinstance(item, dict):
                    loaded.append(DecisionFeedback.from_dict(item))
        self._history = loaded
        # Single aggregate rebuild on load only (not on each feedback).
        self._success_count = sum(1 for entry in self._history if entry.success)
        self._feedback_sum = sum(entry.feedback_score for entry in self._history)
        self._duration_sum = sum(entry.duration for entry in self._history)

    def _save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "confidence_bias": self._confidence_bias,
            "history": [entry.to_dict() for entry in self._history],
            "stats": self.history_stats.to_dict(),
        }
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=4, ensure_ascii=False)
        except OSError as exc:
            logger.warning(
                "Decision history save failed path=%s error=%s",
                self.file_path,
                exc,
            )

    @staticmethod
    def _empty_reason(plan: Plan | None) -> str:
        if plan is None:
            return "No plan available"
        if plan.is_blocked:
            return f"Plan blocked: {plan.blocked_reason or 'unknown'}"
        if plan.status == PlanStatus.COMPLETED or plan.is_completed:
            return "Plan completed — no remaining actions"
        return "No candidate actions"

    @staticmethod
    def _base_priority(
        plan: Plan,
        goal: Any | None,
        project: Any | None,
        mission: Any | None,
        workspace: Any | None,
    ) -> float:
        if plan.priority_score > 0:
            return max(0.0, min(1.0, float(plan.priority_score)))
        return priority_weight(
            getattr(mission, "priority", None)
            or getattr(project, "priority", None)
            or getattr(goal, "priority", None)
            or getattr(workspace, "active_mission_priority", None),
        )

    @staticmethod
    def _base_urgency(
        plan: Plan,
        goal: Any | None,
        project: Any | None,
        mission: Any | None,
        workspace: Any | None,
    ) -> float:
        return priority_weight(
            getattr(mission, "priority", None)
            or getattr(workspace, "active_mission_priority", None)
            or getattr(project, "priority", None)
            or getattr(goal, "priority", None),
        )

    @staticmethod
    def _base_risk(plan: Plan) -> float:
        if plan.is_blocked:
            return 0.95
        if plan.blocked_reason:
            return 0.85
        # More listed dependencies → modest risk uplift (still executable).
        dep_count = len(plan.dependencies or [])
        return max(0.05, min(0.55, 0.08 * dep_count))

    @staticmethod
    def _unmet_dependency_hint(plan: Plan) -> int:
        """Count parent_mission deps as soft blockers for later actions."""
        deps = plan.dependencies or []
        return sum(1 for dep in deps if str(dep).startswith("parent_mission:"))

    @staticmethod
    def _action_priority(base: float, index: int, total: int) -> float:
        # Earlier actions inherit more of the plan priority.
        if total <= 1:
            return base
        position_factor = 1.0 - (0.12 * index)
        return max(0.0, min(1.0, base * position_factor))

    @staticmethod
    def _action_risk(
        base_risk: float,
        index: int,
        total: int,
        unmet_deps: int,
    ) -> float:
        # Later steps and unmet parent deps increase risk (lowers overall score).
        position_penalty = 0.05 * index if total > 1 else 0.0
        dep_penalty = 0.20 * unmet_deps
        return max(0.0, min(1.0, base_risk + position_penalty + dep_penalty))

    @staticmethod
    def _action_dependency(
        index: int,
        total: int,
        unmet_deps: int,
        plan: Plan,
    ) -> float:
        """Dependency readiness — unmet / prior-step deps delay execution."""
        if plan.is_blocked:
            return 0.0
        # Prior steps in the same plan are soft dependencies for later actions.
        prior_step_penalty = 0.22 * index if total > 1 else 0.0
        parent_penalty = 0.35 * unmet_deps
        readiness = 1.0 - prior_step_penalty - parent_penalty
        return max(0.0, min(1.0, readiness))

    @staticmethod
    def _action_estimated_value(
        plan: Plan,
        index: int,
        total: int,
        base_priority: float,
    ) -> float:
        # Prefer immediate next action; shorter plans retain more value.
        if total <= 0:
            return 0.0
        position_value = 1.0 - (0.15 * index)
        duration = plan.estimated_duration
        if duration is None or duration <= 0:
            duration_factor = 0.7
        else:
            # Shorter remaining work → slightly higher expected value.
            duration_factor = max(0.4, min(1.0, 60.0 / (duration + 15.0)))
        return max(0.0, min(1.0, 0.55 * position_value + 0.25 * base_priority + 0.20 * duration_factor))

    @staticmethod
    def _build_reason(
        winner: ActionCandidateScore,
        plan: Plan,
        unmet_deps: int,
    ) -> str:
        parts = [
            f"Selected '{winner.action}' with overall_score={winner.overall_score:.4f}",
            f"priority={winner.priority:.4f}",
            f"urgency={winner.urgency:.4f}",
            f"risk={winner.risk:.4f}",
            f"dependency={winner.dependency:.4f}",
            f"estimated_value={winner.estimated_value:.4f}",
        ]
        if unmet_deps:
            parts.append(f"unmet_parent_deps={unmet_deps}")
        if plan.current_mission:
            parts.append(f"mission={plan.current_mission}")
        return "; ".join(parts)

    def _emit_diagnostics(
        self,
        decision: Decision,
        previous: Decision | None,
    ) -> None:
        is_create = previous is None
        action_changed = (
            previous is not None
            and previous.selected_action != decision.selected_action
        )
        scores_changed = (
            previous is not None
            and not is_create
            and (
                previous.confidence != decision.confidence
                or previous.priority != decision.priority
                or previous.risk_score != decision.risk_score
                or previous.expected_value != decision.expected_value
                or previous.reason != decision.reason
            )
        )

        if is_create:
            logger.info(
                "DECISION_CREATED action=%s confidence=%s priority=%s "
                "risk=%s expected_value=%s candidates=%s",
                decision.selected_action,
                decision.confidence,
                decision.priority,
                decision.risk_score,
                decision.expected_value,
                len(decision.candidates),
            )
        elif action_changed or scores_changed:
            logger.info(
                "DECISION_UPDATED action=%s confidence=%s priority=%s "
                "risk=%s expected_value=%s previous_action=%s",
                decision.selected_action,
                decision.confidence,
                decision.priority,
                decision.risk_score,
                decision.expected_value,
                previous.selected_action if previous else None,
            )

        if decision.selected_action is not None:
            logger.info(
                "DECISION_SELECTED action=%s confidence=%s priority=%s "
                "risk=%s expected_value=%s reason=%s",
                decision.selected_action,
                decision.confidence,
                decision.priority,
                decision.risk_score,
                decision.expected_value,
                decision.reason,
            )

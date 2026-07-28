# =====================================
# Titan Decision System
# =====================================

"""Backward-compatible facade over DecisionEngine (Phase 17.3–17.4).

Legacy ``decide(message)`` remains for debug-only intent classification.
``decide_next`` / ``engine`` expose the cognitive Decision Engine that
selects among PlanningEngine next-actions and learns from feedback.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from brain.decision_engine import DecisionEngine
from brain.decision_models import Decision as DecisionResult
from brain.decision_models import DecisionFeedback
from brain.planning_models import Plan


class Decision:
    """Legacy decision interface — delegates next-action selection to DecisionEngine."""

    def __init__(self, engine: DecisionEngine | None = None) -> None:
        self._engine = engine or DecisionEngine()

    @property
    def engine(self) -> DecisionEngine:
        return self._engine

    def decide(self, message: str) -> str:
        """Debug-only coarse intent class (not the Phase 17.3 Decision Engine)."""
        if "bonjour" in message.lower():
            return "salutation"
        return "conversation"

    def decide_next(
        self,
        *,
        plan: Plan | None = None,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        now: datetime | None = None,
    ) -> DecisionResult:
        """Select the next action from the current plan (Phase 17.3)."""
        return self._engine.decide(
            plan=plan,
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            now=now,
        )

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
        """Record execution feedback for decision learning (Phase 17.4)."""
        return self._engine.record_feedback(
            actual_result=actual_result,
            success=success,
            duration=duration,
            decision_id=decision_id,
            selected_action=selected_action,
            expected_value=expected_value,
            now=now,
        )

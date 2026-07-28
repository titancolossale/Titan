# =====================================
# Titan Planning System
# =====================================

"""Backward-compatible facade over PlanningEngine (Phase 8 — P8-032).

Phase 17.1 — also exposes ``plan_next`` for WorkspaceState-driven next-action
planning.
Phase 17.2 — ``plan_next`` accepts optional ``change_reason`` for evolution
triggers (mission completed / blocked, goal / project / workspace change).
"""

from __future__ import annotations

from typing import Any, Callable

from brain.planning_engine import PlanningEngine
from brain.planning_models import Plan


class Planning:
    """Legacy planning interface — delegates to PlanningEngine."""

    def __init__(self, engine: PlanningEngine | None = None) -> None:
        self._engine = engine or PlanningEngine()

    @property
    def engine(self) -> PlanningEngine:
        return self._engine

    def create_plan(self, goal: str, mission: dict | None = None) -> list[str]:
        """Return step descriptions for debug compatibility."""
        plan = self._engine.create_plan(goal, mission=mission)
        return [step.description for step in plan.steps]

    def plan_next(
        self,
        *,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        mission_lookup: Callable[[str], Any | None] | None = None,
        change_reason: str | None = None,
    ) -> Plan:
        """Build or evolve the next execution plan from workspace hierarchy."""
        return self._engine.plan_next(
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            mission_lookup=mission_lookup,
            change_reason=change_reason,
        )

    def complete_plan(self, plan: Plan | None = None) -> Plan:
        """Mark the active plan completed."""
        return self._engine.complete_plan(plan)

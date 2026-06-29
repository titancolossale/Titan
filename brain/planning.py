# =====================================
# Titan Planning System
# =====================================

"""Backward-compatible facade over PlanningEngine (Phase 8 — P8-032)."""

from __future__ import annotations

from brain.planning_engine import PlanningEngine


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

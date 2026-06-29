# =====================================
# Titan Planning Engine Tests
# =====================================

"""Tests for Phase 8 PlanningEngine (P8-030–P8-040)."""

from __future__ import annotations

import pytest

from brain.brain import Brain
from brain.planning_engine import PlanningEngine
from brain.planning_models import StructuredPlan


@pytest.fixture
def engine() -> PlanningEngine:
    return PlanningEngine()


ACTIVE_TRADING_MISSION = {
    "active": True,
    "title": "Créer un robot de trading",
    "objective": "Robot NQ",
    "steps": ["Backtest", "Execution"],
    "completed_steps": [],
    "current_step": "Backtest",
    "status": "in_progress",
}


def test_create_plan_without_mission_returns_generic_steps(
    engine: PlanningEngine,
) -> None:
    """P8-031: open goal produces generic 4-step plan."""
    plan = engine.create_plan("Explique Python")
    assert isinstance(plan, StructuredPlan)
    assert len(plan.steps) == 4
    assert plan.mission_step is None
    assert plan.domain in ("general", "coding")


def test_create_plan_with_mission_links_current_step(
    engine: PlanningEngine,
) -> None:
    """P8-031: active mission links plan to current_step."""
    plan = engine.create_plan(
        "Continue le backtest",
        mission=ACTIVE_TRADING_MISSION,
    )
    assert plan.mission_step == "Backtest"
    assert plan.current_focus == "Backtest"
    assert all(
        step.linked_mission_step == "Backtest" for step in plan.steps
    )


def test_create_plan_detects_trading_domain(
    engine: PlanningEngine,
) -> None:
    """P8-031: trading keywords set domain for future automation hooks."""
    plan = engine.create_plan(
        "Configure le backtest NQ",
        mission=ACTIVE_TRADING_MISSION,
    )
    assert plan.domain == "trading"


def test_format_for_prompt_includes_mission_step(
    engine: PlanningEngine,
) -> None:
    """P8-032: formatted plan includes mission step for PromptBuilder."""
    plan = engine.create_plan("Avance", mission=ACTIVE_TRADING_MISSION)
    text = plan.format_for_prompt()
    assert "Backtest" in text
    assert "Plan d'action" in text


def test_planning_facade_delegates_to_engine() -> None:
    """P8-032: legacy Planning.create_plan returns description strings."""
    from brain.planning import Planning

    planning = Planning()
    steps = planning.create_plan("Test goal")
    assert isinstance(steps, list)
    assert all(isinstance(s, str) for s in steps)
    assert len(steps) >= 3


def test_brain_think_includes_plan_in_prompt(brain: Brain) -> None:
    """P8-033: structured plan appears in LLM prompt."""
    brain.mission_manager.create_mission(
        "Trading",
        "NQ bot",
        ["Backtest", "Live"],
    )

    brain.think("Continue le backtest")

    prompt = brain.llm.ask.call_args[0][0]
    assert "PLAN D'ACTION" in prompt
    assert "Backtest" in prompt


def test_create_plan_stage_in_pipeline_order() -> None:
    """P8-033: create_plan runs after executive_analysis."""
    from brain.pipeline.stages import STAGE_ORDER

    assert "create_plan" in STAGE_ORDER
    assert STAGE_ORDER.index("create_plan") > STAGE_ORDER.index("executive_analysis")
    assert STAGE_ORDER.index("create_plan") < STAGE_ORDER.index("execution_coordinate")

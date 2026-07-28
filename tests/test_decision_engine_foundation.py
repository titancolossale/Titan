# =====================================
# Titan Decision Engine Foundation Tests
# =====================================

"""Phase 17.3 Decision Engine — select next action from plan candidates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brain.brain import Brain
from brain.decision import Decision as DecisionFacade
from brain.decision_engine import DecisionEngine
from brain.decision_models import (
    Decision,
    compute_confidence,
    compute_overall_score,
)
from brain.pipeline.context_bundle import ThinkContext
from brain.pipeline.stages import STAGE_ORDER
from brain.planning_engine import PlanningEngine
from brain.planning_models import Plan, PlanStatus
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_models import GoalPriority
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.project_manager import ProjectManager
from core.project_models import ProjectPriority
from core.state_manager import StateManager


REQUIRED_DECISION_FIELDS = {
    "selected_action",
    "reason",
    "confidence",
    "priority",
    "risk_score",
    "expected_value",
    "created_at",
    "decision_id",
}


def _assert_required_fields(decision: Decision) -> None:
    payload = decision.to_dict()
    assert REQUIRED_DECISION_FIELDS.issubset(payload.keys())


def _paired_managers(
    tmp_path: Path,
) -> tuple[StateManager, GoalManager, ProjectManager, MissionManager]:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    goals = GoalManager(
        file_path=tmp_path / "titan_goals.json",
        state_manager=state,
    )
    projects = ProjectManager(
        file_path=tmp_path / "titan_projects.json",
        state_manager=state,
        goal_manager=goals,
    )
    missions = MissionManager(
        file_path=tmp_path / "titan_mission.json",
        state_manager=state,
        project_manager=projects,
    )
    goals.bind_project_manager(projects)
    goals.bind_mission_manager(missions)
    return state, goals, projects, missions


def _make_plan(
    *,
    actions: list[str],
    priority_score: float = 0.75,
    dependencies: list[str] | None = None,
    blocked_reason: str | None = None,
    status: PlanStatus = PlanStatus.ACTIVE,
    estimated_duration: float | None = 30.0,
) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan",
        current_project="Decision Engine",
        current_mission="Foundation",
        next_actions=list(actions),
        priority_score=priority_score,
        estimated_duration=estimated_duration,
        dependencies=list(dependencies or []),
        blocked_reason=blocked_reason,
        created_at=stamp,
        updated_at=stamp,
        status=status,
    )


# ---------------------------------------------------------------------------
# Highest score is selected
# ---------------------------------------------------------------------------


def test_highest_score_is_selected(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Ship Titan", priority=GoalPriority.HIGH)
    project = projects.create_project(
        "Decision Engine",
        priority=ProjectPriority.HIGH,
        goal_id=goal.id,
    )
    mission = missions.create_mission(
        "Foundation",
        "Build decision engine",
        ["Design models", "Wire Brain", "Add tests"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )
    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
        mission_lookup=missions.runtime.get_mission,
    )

    decision = DecisionEngine(persist=False).decide(
        plan=plan,
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=mission,
    )

    _assert_required_fields(decision)
    assert decision.selected_action == plan.next_actions[0]
    assert decision.candidates
    assert decision.candidates[0].overall_score == max(
        c.overall_score for c in decision.candidates
    )
    assert decision.selected_action == decision.candidates[0].action


def test_overall_score_formula_prefers_value_over_risk() -> None:
    low_risk = compute_overall_score(
        priority=0.8,
        urgency=0.8,
        risk=0.1,
        dependency=0.9,
        estimated_value=0.9,
    )
    high_risk = compute_overall_score(
        priority=0.8,
        urgency=0.8,
        risk=0.9,
        dependency=0.9,
        estimated_value=0.9,
    )
    assert low_risk > high_risk


# ---------------------------------------------------------------------------
# Risk lowers score
# ---------------------------------------------------------------------------


def test_risk_lowers_score() -> None:
    engine = DecisionEngine(persist=False)
    safe_plan = _make_plan(actions=["Safe action"], dependencies=[], priority_score=0.8)
    risky_plan = _make_plan(
        actions=["Risky action"],
        dependencies=["parent_mission:abc", "parent_mission:def"],
        priority_score=0.8,
    )

    safe = engine.decide(plan=safe_plan)
    # Fresh engine so diagnostics / active state do not interfere with compare.
    risky = DecisionEngine(persist=False).decide(plan=risky_plan)

    assert risky.candidates[0].risk > safe.candidates[0].risk
    assert risky.candidates[0].overall_score < safe.candidates[0].overall_score
    assert risky.risk_score > safe.risk_score


def test_blocked_plan_yields_no_selection() -> None:
    plan = _make_plan(
        actions=[],
        blocked_reason="Waiting on dependency",
        status=PlanStatus.BLOCKED,
    )
    decision = DecisionEngine(persist=False).decide(plan=plan)
    assert decision.selected_action is None
    assert decision.confidence == 0.0
    assert "blocked" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Priority increases score
# ---------------------------------------------------------------------------


def test_priority_increases_score(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Priority Goal", priority=GoalPriority.NORMAL)
    project = projects.create_project(
        "Priority Project",
        priority=ProjectPriority.NORMAL,
        goal_id=goal.id,
    )
    low_mission = missions.create_mission(
        "Low Mission",
        steps=["Low step"],
        priority=MissionPriority.LOW,
        project_id=project.id,
    )
    missions.pause_mission(low_mission.id)
    high_mission = missions.create_mission(
        "High Mission",
        steps=["High step"],
        priority=MissionPriority.CRITICAL,
        project_id=project.id,
    )

    low_plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=low_mission,
    )
    high_plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=high_mission,
    )

    low_decision = DecisionEngine(persist=False).decide(
        plan=low_plan,
        goal=goal,
        project=project,
        mission=low_mission,
    )
    high_decision = DecisionEngine(persist=False).decide(
        plan=high_plan,
        goal=goal,
        project=project,
        mission=high_mission,
    )

    assert high_decision.priority > low_decision.priority
    assert high_decision.candidates[0].overall_score > low_decision.candidates[0].overall_score


def test_priority_weight_in_overall_formula() -> None:
    low = compute_overall_score(
        priority=0.25,
        urgency=0.5,
        risk=0.2,
        dependency=0.8,
        estimated_value=0.5,
    )
    high = compute_overall_score(
        priority=1.0,
        urgency=0.5,
        risk=0.2,
        dependency=0.8,
        estimated_value=0.5,
    )
    assert high > low


# ---------------------------------------------------------------------------
# Dependencies delay execution
# ---------------------------------------------------------------------------


def test_dependencies_delay_later_actions() -> None:
    plan = _make_plan(
        actions=["First", "Second", "Third"],
        dependencies=["step:Second", "step:Third"],
        priority_score=0.7,
    )
    decision = DecisionEngine(persist=False).decide(plan=plan)

    by_action = {c.action: c for c in decision.candidates}
    assert by_action["First"].dependency > by_action["Second"].dependency
    assert by_action["Second"].dependency > by_action["Third"].dependency
    assert by_action["First"].overall_score > by_action["Third"].overall_score
    assert decision.selected_action == "First"


def test_unmet_parent_dependency_delays_selection(tmp_path: Path) -> None:
    state, goals, projects, missions = _paired_managers(tmp_path)
    goal = goals.create_goal("Deps Goal")
    project = projects.create_project("Deps Project", goal_id=goal.id)
    parent = missions.create_mission(
        "Parent Mission",
        steps=["Parent work"],
        project_id=project.id,
    )
    child = missions.create_mission(
        "Child Mission",
        steps=["Child A", "Child B"],
        parent_mission=parent.id,
        project_id=project.id,
    )

    # Plan is blocked with empty actions when parent unmet — decision stays empty.
    plan = PlanningEngine().plan_next(
        workspace=state.load(),
        goal=goal,
        project=project,
        mission=child,
        mission_lookup=missions.runtime.get_mission,
    )
    decision = DecisionEngine(persist=False).decide(
        plan=plan,
        goal=goal,
        project=project,
        mission=child,
    )
    assert plan.is_blocked
    assert decision.selected_action is None

    # When actions exist with parent_mission deps listed, dependency score drops.
    soft = _make_plan(
        actions=["Child A", "Child B"],
        dependencies=[f"parent_mission:{parent.id}"],
        priority_score=0.6,
    )
    soft_decision = DecisionEngine(persist=False).decide(plan=soft)
    assert soft_decision.selected_action == "Child A"
    assert soft_decision.candidates[0].dependency < 1.0
    assert soft_decision.candidates[-1].dependency < soft_decision.candidates[0].dependency


# ---------------------------------------------------------------------------
# Confidence is computed
# ---------------------------------------------------------------------------


def test_confidence_is_computed() -> None:
    plan = _make_plan(actions=["Only action"], priority_score=0.9)
    decision = DecisionEngine(persist=False).decide(plan=plan)
    assert 0.0 < decision.confidence <= 1.0
    assert decision.confidence == compute_confidence(
        top_score=decision.candidates[0].overall_score,
        second_score=None,
        candidate_count=1,
    )


def test_confidence_lower_when_near_tie() -> None:
    clear = compute_confidence(top_score=0.9, second_score=0.2, candidate_count=2)
    tie = compute_confidence(top_score=0.55, second_score=0.54, candidate_count=2)
    assert clear > tie


def test_decision_format_for_prompt_includes_required_sections() -> None:
    plan = _make_plan(actions=["Do the thing", "Then another"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    text = decision.format_for_prompt()
    assert "Current Decision:" in text
    assert "Reason:" in text
    assert "Current Confidence:" in text
    assert "Success Rate:" in text
    assert "Recent Decision History:" in text
    assert "Top Candidate Actions:" in text
    assert "Do the thing" in text


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_decision_diagnostics_emitted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _make_plan(actions=["Alpha", "Beta"], priority_score=0.8)
    engine = DecisionEngine(persist=False)

    with caplog.at_level(logging.INFO, logger="brain.decision_engine"):
        first = engine.decide(plan=plan)
        second_plan = _make_plan(actions=["Beta", "Alpha"], priority_score=0.8)
        second = engine.decide(plan=second_plan)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("DECISION_CREATED") for msg in messages)
    assert any(msg.startswith("DECISION_SELECTED") for msg in messages)
    assert first.selected_action == "Alpha"
    assert second.selected_action == "Beta"
    assert any(msg.startswith("DECISION_UPDATED") for msg in messages)


# ---------------------------------------------------------------------------
# Performance — single evaluation pass, no duplicated scoring
# ---------------------------------------------------------------------------


def test_single_evaluation_pass_no_duplicate_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}
    original = compute_overall_score

    def counted(*args, **kwargs):
        call_count["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "brain.decision_engine.compute_overall_score",
        counted,
    )
    plan = _make_plan(actions=["A", "B", "C", "D"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    assert call_count["n"] == len(plan.next_actions)
    assert len(decision.candidates) == len(plan.next_actions)


def test_pipeline_stage_order_includes_create_decision() -> None:
    assert "create_decision" in STAGE_ORDER
    assert STAGE_ORDER.index("create_decision") > STAGE_ORDER.index("create_plan")
    assert STAGE_ORDER.index("create_decision") < STAGE_ORDER.index(
        "execution_coordinate"
    )


# ---------------------------------------------------------------------------
# Prompt builder + Brain wiring
# ---------------------------------------------------------------------------


def test_prompt_builder_injects_current_decision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _make_plan(actions=["Ship it"])
    decision = DecisionEngine(persist=False).decide(plan=plan)
    ctx = ThinkContext(
        user_message="Go",
        current_user="Nolan",
        decision_text=decision.format_for_prompt(),
        execution_decision=decision,
    )
    with caplog.at_level(logging.INFO, logger="brain.prompt_builder"):
        prompt = PromptBuilder().build(ctx)

    assert "DÉCISION ACTUELLE" in prompt
    assert "Current Decision:" in prompt
    assert "Ship it" in prompt
    assert "Current Confidence:" in prompt
    assert "Success Rate:" in prompt
    assert "Recent Decision History:" in prompt
    assert "Top Candidate Actions:" in prompt
    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("DECISION_PROMPT_ATTACHED") for msg in messages)


def test_decision_facade_exposes_engine() -> None:
    facade = DecisionFacade()
    assert isinstance(facade.engine, DecisionEngine)
    assert facade.decide("bonjour") == "salutation"
    plan = _make_plan(actions=["Next"])
    result = facade.decide_next(plan=plan)
    assert result.selected_action == "Next"


def test_brain_wires_decision_engine(brain: Brain) -> None:
    assert isinstance(brain.decision, DecisionFacade)
    assert isinstance(brain.decision.engine, DecisionEngine)
    assert hasattr(brain.decision, "decide_next")
    assert "create_decision" in STAGE_ORDER


def test_brain_think_includes_execution_decision(brain: Brain) -> None:
    brain.goal_manager.create_goal("Decision Goal")
    project = brain.project_manager.create_project("Decision Project")
    brain.mission_manager.create_mission(
        "Decision Mission",
        "Pick next action",
        ["Design", "Wire", "Test"],
        project_id=project.id,
    )

    brain.think("Continue")

    prompt = brain.llm.ask.call_args[0][0]
    assert "DÉCISION ACTUELLE" in prompt
    assert "Current Decision:" in prompt
    assert "Design" in prompt
    assert "Current Confidence:" in prompt
    assert "Success Rate:" in prompt
    assert "Recent Decision History:" in prompt
    assert "Top Candidate Actions:" in prompt

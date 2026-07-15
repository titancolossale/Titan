# =====================================
# Titan Reasoning Loop Tests
# =====================================

"""Tests for Phase 12.6 Batch 3 — Reasoning Loop (P126-022)."""

from __future__ import annotations

import pytest

from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport
from tools.natural_language_planner import compute_execution_order
from tools.permission_manager import PermissionLevel
from tools.planner_models import (
    ExecutionPlan,
    PlannerResult,
    PlanStep,
    PlanStepKind,
    ReviewedPlannerResult,
)
from tools.reasoning_loop import ReasoningLoop, reasoning_clarification_tool_result
from tools.tool_enums import RiskLevel


@pytest.fixture
def reasoning_loop() -> ReasoningLoop:
    return ReasoningLoop()


def _planner_result_from_steps(
    steps: tuple[PlanStep, ...],
    *,
    goal: str = "Test goal",
    summary: str = "Test summary",
    requires_confirmation: bool = False,
) -> PlannerResult:
    order = compute_execution_order(steps)
    plan = ExecutionPlan(
        overall_goal=goal,
        plan_summary=summary,
        steps=steps,
        execution_order=order,
    )
    return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)


def _basic_step(
    step_id: str,
    *,
    tool: str = "time",
    action: str = "get_time",
    permission: PermissionLevel = PermissionLevel.AUTO_ALLOWED,
    params: dict | None = None,
    dependencies: tuple[str, ...] = (),
    step_kind: PlanStepKind = PlanStepKind.STANDARD,
) -> PlanStep:
    tool_params = dict(params or {})
    if action and "action" not in tool_params:
        tool_params["action"] = action
    return PlanStep(
        step_id=step_id,
        objective=f"Run {action}",
        reasoning="Test step",
        required_tool=tool,
        required_permission=permission,
        expected_output="Result",
        dependencies=dependencies,
        tool_params=tool_params,
        selected_action=action,
        step_kind=step_kind,
    )


# ---------------------------------------------------------------------------
# P126-022 — ReviewedPlannerResult model
# ---------------------------------------------------------------------------


def test_reviewed_planner_result_from_planner_result() -> None:
    step = _basic_step("step_1")
    planner_result = _planner_result_from_steps((step,))
    reviewed = ReviewedPlannerResult.from_planner_result(planner_result)

    assert reviewed.overall_goal == "Test goal"
    assert reviewed.total_steps == 1
    assert reviewed.confidence_score == 1.0
    assert reviewed.clarification_required is False
    assert reviewed.optimization_count == 0
    assert reviewed.get_step("step_1") is step


def test_reviewed_planner_result_serialization_roundtrip() -> None:
    step = _basic_step("step_1")
    planner_result = _planner_result_from_steps((step,))
    original = ReviewedPlannerResult.from_planner_result(
        planner_result,
        confidence_score=0.85,
        reasoning_summary="Plan validé.",
        optimization_count=2,
        review_issues=("ordre corrigé",),
    )
    restored = ReviewedPlannerResult.from_dict(original.to_dict())

    assert restored.confidence_score == 0.85
    assert restored.optimization_count == 2
    assert restored.review_issues == ("ordre corrigé",)
    assert restored.total_steps == 1


def test_reasoning_clarification_tool_result() -> None:
    reviewed = ReviewedPlannerResult.from_planner_result(
        _planner_result_from_steps(()),
        clarification_required=True,
        clarification_message="Chemin de fichier manquant.",
        confidence_score=0.4,
        reasoning_summary="Clarification requise.",
    )
    result = reasoning_clarification_tool_result(reviewed)

    assert result.success is False
    assert "Clarification requise" in (result.error or "")
    assert result.metadata.get("clarification_required") is True


# ---------------------------------------------------------------------------
# P126-022 — Plan review and safe optimization
# ---------------------------------------------------------------------------


def test_review_passes_valid_plan_unchanged(reasoning_loop: ReasoningLoop) -> None:
    step = _basic_step("step_1")
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.clarification_required is False
    assert reviewed.optimization_count == 0
    assert reviewed.confidence_score >= 0.9
    assert reviewed.total_steps == 1
    assert "validé" in reviewed.reasoning_summary.lower()


def test_review_removes_redundant_steps(reasoning_loop: ReasoningLoop) -> None:
    duplicate_a = _basic_step("step_a")
    duplicate_b = _basic_step("step_b")
    planner_result = _planner_result_from_steps((duplicate_a, duplicate_b))

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.total_steps == 1
    assert reviewed.optimization_count >= 1
    assert reviewed.clarification_required is False


def test_review_fixes_execution_order(reasoning_loop: ReasoningLoop) -> None:
    step_b = _basic_step(
        "step_b",
        tool="file_read",
        action="read_file",
        params={"path": "a.txt"},
        dependencies=("step_a",),
    )
    step_a = _basic_step(
        "step_a",
        tool="file_read",
        action="search_files",
        params={"keyword": "a"},
    )
    plan = ExecutionPlan(
        overall_goal="Read after search",
        plan_summary="Wrong order",
        steps=(step_b, step_a),
        execution_order=("step_b", "step_a"),
    )
    planner_result = PlannerResult.from_execution_plan(plan)

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.execution_order.index("step_a") < reviewed.execution_order.index("step_b")
    assert reviewed.optimization_count >= 1


def test_review_fixes_invalid_dependencies(reasoning_loop: ReasoningLoop) -> None:
    step = _basic_step(
        "step_1",
        tool="file_read",
        action="read_file",
        params={"path": "readme.txt"},
        dependencies=("missing_step",),
    )
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result)

    cleaned = reviewed.get_step("step_1")
    assert cleaned is not None
    assert cleaned.dependencies == ()
    assert reviewed.optimization_count >= 1


def test_review_syncs_permission_drift(reasoning_loop: ReasoningLoop) -> None:
    step = _basic_step(
        "step_1",
        tool="obsidian",
        action="delete_note",
        permission=PermissionLevel.AUTO_ALLOWED,
        params={"note": "test.md", "action": "delete_note"},
    )
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result)

    synced = reviewed.get_step("step_1")
    assert synced is not None
    assert synced.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
    assert reviewed.requires_confirmation is True
    assert reviewed.optimization_count >= 1


def test_review_inserts_search_before_obsidian_create(reasoning_loop: ReasoningLoop) -> None:
    create_step = _basic_step(
        "create",
        tool="obsidian",
        action="create_note",
        params={"title": "Projet Titan", "action": "create_note"},
    )
    planner_result = _planner_result_from_steps((create_step,))

    reviewed = reasoning_loop.review(
        planner_result,
        message="Crée une note Projet Titan",
    )

    assert reviewed.total_steps == 2
    assert reviewed.optimization_count >= 1
    search_step = next(
        step for step in reviewed.steps if step.tool_params.get("action") == "search_notes"
    )
    assert search_step.tool_params.get("query") == "Projet Titan"
    create = reviewed.get_step("create")
    assert create is not None
    assert search_step.step_id in create.dependencies


def test_review_requests_clarification_for_missing_path(reasoning_loop: ReasoningLoop) -> None:
    step = _basic_step(
        "read",
        tool="file_read",
        action="read_file",
        params={"action": "read_file"},
    )
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.clarification_required is True
    assert reviewed.confidence_score < 0.6
    assert "path" in reviewed.clarification_message.lower()


def test_review_requests_clarification_for_blocked_step(reasoning_loop: ReasoningLoop) -> None:
    step = _basic_step(
        "blocked",
        tool="unknown_tool",
        action="run",
        permission=PermissionLevel.BLOCKED,
        params={"action": "run"},
    )
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.clarification_required is True
    assert "bloquée" in reviewed.clarification_message.lower()


def test_review_honors_needs_clarification_analysis(reasoning_loop: ReasoningLoop) -> None:
    planner_result = _planner_result_from_steps(())
    reviewed = reasoning_loop.review(
        planner_result,
        analysis={"needs_clarification": True},
    )

    assert reviewed.clarification_required is True
    assert reviewed.confidence_score <= 0.3


def test_review_does_not_invent_search_query_for_create(reasoning_loop: ReasoningLoop) -> None:
    create_step = _basic_step(
        "create",
        tool="obsidian",
        action="create_note",
        params={"action": "create_note"},
    )
    planner_result = _planner_result_from_steps((create_step,))

    reviewed = reasoning_loop.review(planner_result, message="")

    assert reviewed.total_steps == 1
    assert not any(
        step.tool_params.get("action") == "search_notes" for step in reviewed.steps
    )


def test_review_empty_plan(reasoning_loop: ReasoningLoop) -> None:
    planner_result = _planner_result_from_steps(())

    reviewed = reasoning_loop.review(planner_result)

    assert reviewed.total_steps == 0
    assert reviewed.clarification_required is False


def test_review_with_decision_report(reasoning_loop: ReasoningLoop) -> None:
    report = ToolDecisionReport(
        intent=Intent.OBSIDIAN,
        confidence=0.9,
        tool_required=True,
        candidate_tools=("obsidian",),
        selected_tool="obsidian",
        decision_reason="obsidian update",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        obsidian_action="patch_note",
    )
    step = _basic_step(
        "patch",
        tool="obsidian",
        action="patch_note",
        params={
            "note": "notes/test.md",
            "action": "patch_note",
            "mode": "append",
            "content": "x",
        },
    )
    planner_result = _planner_result_from_steps((step,))

    reviewed = reasoning_loop.review(planner_result, decision_report=report)

    assert reviewed.clarification_required is False
    assert reviewed.get_step("patch") is not None

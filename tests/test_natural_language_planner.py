# =====================================
# Titan Natural Language Planner Tests
# =====================================

"""Tests for Phase 12.6 Batch 2 — Natural Language Planner (P126-012)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport
from tools.decision.task_execution_models import TaskExecutionPlan, TaskStepDefinition
from tools.decision.workspace_planner import WorkspacePlan
from tools.natural_language_planner import (
    NaturalLanguagePlanner,
    compute_execution_order,
    identify_independent_steps,
    identify_sequential_steps,
)
from tools.orchestration_models import OrchestrationStatus
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.planner_models import (
    ExecutionPlan,
    PlannerResult,
    PlanStep,
    PlanStepKind,
)
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest, ToolResult


@pytest.fixture
def planner() -> NaturalLanguagePlanner:
    return NaturalLanguagePlanner()


def _basic_analysis(
    *,
    message: str = "Quelle heure est-il ?",
    tool_requests: list[ToolRequest] | None = None,
    needs_tool: bool = True,
    needs_clarification: bool = False,
    **extra,
) -> dict:
    report = ToolDecisionReport(
        intent=Intent.SYSTEM,
        confidence=0.9,
        tool_required=needs_tool,
        candidate_tools=("time",),
        selected_tool="time",
        decision_reason="time request",
        risk_level=RiskLevel.SAFE,
        confirmation_required=False,
    )
    return {
        "message": message,
        "goal": "Comprendre la demande",
        "needs_memory": False,
        "needs_tool": needs_tool,
        "needs_clarification": needs_clarification,
        "tool_requests": (
            tool_requests
            if tool_requests is not None
            else [ToolRequest("time", {})]
        ),
        "decision_report": report,
        **extra,
    }


# ---------------------------------------------------------------------------
# P126-012 — PlannerResult and ExecutionPlan models
# ---------------------------------------------------------------------------


def test_planner_result_from_execution_plan() -> None:
    step = PlanStep(
        step_id="step_1",
        objective="Get time",
        reasoning="Single-step",
        required_tool="time",
        required_permission=PermissionLevel.AUTO_ALLOWED,
        expected_output="Current datetime",
    )
    plan = ExecutionPlan(
        overall_goal="What time is it?",
        plan_summary="One step",
        steps=(step,),
        execution_order=("step_1",),
    )
    result = PlannerResult.from_execution_plan(plan)

    assert result.overall_goal == "What time is it?"
    assert result.plan_summary == "One step"
    assert result.total_steps == 1
    assert result.estimated_tools == ("time",)
    assert result.requires_confirmation is False
    assert result.execution_order == ("step_1",)
    assert result.get_step("step_1") is step


def test_plan_step_serialization_roundtrip() -> None:
    step = PlanStep(
        step_id="read",
        objective="Read file",
        reasoning="Depends on search",
        required_tool="file_read",
        required_permission=PermissionLevel.AUTO_ALLOWED,
        expected_output="File contents",
        dependencies=("search",),
        tool_params={"action": "read_file", "path": "readme.txt"},
        step_kind=PlanStepKind.CONDITIONAL,
        condition="search_has_results",
    )
    restored = PlanStep.from_dict(step.to_dict())
    assert restored == step


def test_execution_plan_reusable_object() -> None:
    steps = (
        PlanStep(
            step_id="a",
            objective="A",
            reasoning="Independent",
            required_tool="time",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="t",
        ),
        PlanStep(
            step_id="b",
            objective="B",
            reasoning="Sequential",
            required_tool="file_read",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="f",
            dependencies=("a",),
        ),
    )
    plan = ExecutionPlan(
        overall_goal="Multi",
        plan_summary="Two steps",
        steps=steps,
        execution_order=("a", "b"),
    )
    restored = ExecutionPlan.from_dict(plan.to_dict())
    assert restored.overall_goal == plan.overall_goal
    assert restored.total_steps == 2
    assert restored.estimated_tools == ("time", "file_read")


def test_planner_result_to_dict_contains_required_fields() -> None:
    step = PlanStep(
        step_id="step_1",
        objective="obj",
        reasoning="why",
        required_tool="time",
        required_permission=PermissionLevel.AUTO_ALLOWED,
        expected_output="out",
    )
    plan = ExecutionPlan(
        overall_goal="goal",
        plan_summary="summary",
        steps=(step,),
        execution_order=("step_1",),
    )
    result = PlannerResult.from_execution_plan(plan, requires_confirmation=False)
    payload = result.to_dict()

    assert payload["overall_goal"] == "goal"
    assert payload["plan_summary"] == "summary"
    assert payload["total_steps"] == 1
    assert payload["estimated_tools"] == ["time"]
    assert payload["requires_confirmation"] is False
    assert payload["execution_order"] == ["step_1"]


# ---------------------------------------------------------------------------
# P126-012 — Execution order and dependency analysis
# ---------------------------------------------------------------------------


def test_compute_execution_order_respects_dependencies() -> None:
    steps = (
        PlanStep(
            step_id="read",
            objective="Read",
            reasoning="After search",
            required_tool="file_read",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="content",
            dependencies=("search",),
        ),
        PlanStep(
            step_id="search",
            objective="Search",
            reasoning="First",
            required_tool="file_read",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="paths",
        ),
    )
    order = compute_execution_order(steps)
    assert order.index("search") < order.index("read")


def test_identify_independent_and_sequential_steps() -> None:
    steps = (
        PlanStep(
            step_id="a",
            objective="A",
            reasoning="Independent",
            required_tool="time",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="t",
        ),
        PlanStep(
            step_id="b",
            objective="B",
            reasoning="Sequential",
            required_tool="file_read",
            required_permission=PermissionLevel.AUTO_ALLOWED,
            expected_output="f",
            dependencies=("a",),
        ),
    )
    assert identify_independent_steps(steps) == ("a",)
    assert identify_sequential_steps(steps) == ("b",)


# ---------------------------------------------------------------------------
# P126-012 — Single-step and multi-step planning
# ---------------------------------------------------------------------------


def test_single_step_plan(planner: NaturalLanguagePlanner) -> None:
    analysis = _basic_analysis(message="Quelle heure est-il ?")
    result = planner.plan("Quelle heure est-il ?", analysis)

    assert result.total_steps == 1
    assert result.estimated_tools == ("time",)
    assert result.execution_order == ("step_1",)
    step = result.get_step("step_1")
    assert step is not None
    assert step.required_tool == "time"
    assert step.required_permission == PermissionLevel.AUTO_ALLOWED
    assert step.dependencies == ()


def test_multi_step_plan(planner: NaturalLanguagePlanner) -> None:
    requests = [
        ToolRequest("file_read", {"action": "search_files", "keyword": "context"}),
        ToolRequest("file_read", {"action": "read_file", "path": "readme.txt"}),
    ]
    analysis = _basic_analysis(
        message="Cherche context puis lis readme",
        tool_requests=requests,
    )
    result = planner.plan("Cherche context puis lis readme", analysis)

    assert result.total_steps == 2
    assert len(result.estimated_tools) == 1
    assert result.execution_order == ("step_1", "step_2")
    second = result.get_step("step_2")
    assert second is not None
    assert second.dependencies == ("step_1",)


def test_empty_plan_when_no_tools(planner: NaturalLanguagePlanner) -> None:
    analysis = _basic_analysis(
        needs_tool=False,
        tool_requests=[],
    )
    result = planner.plan("Bonjour", analysis)
    assert result.total_steps == 0
    assert result.estimated_tools == ()


def test_clarification_produces_empty_plan(planner: NaturalLanguagePlanner) -> None:
    analysis = _basic_analysis(
        needs_clarification=True,
        needs_tool=False,
        tool_requests=[],
    )
    result = planner.plan("Fais quelque chose", analysis)
    assert result.total_steps == 0
    assert "Clarification" in result.plan_summary


# ---------------------------------------------------------------------------
# P126-012 — Conditional and fallback steps
# ---------------------------------------------------------------------------


def test_conditional_plan_from_message(planner: NaturalLanguagePlanner) -> None:
    requests = [ToolRequest("file_read", {"action": "read_file", "path": "a.txt"})]
    analysis = _basic_analysis(
        message="Lis a.txt si le fichier existe sinon cherche",
        tool_requests=requests,
    )
    result = planner.plan("Lis a.txt si le fichier existe sinon cherche", analysis)

    assert result.total_steps >= 2
    kinds = {step.step_kind for step in result.steps}
    assert PlanStepKind.CONDITIONAL in kinds or PlanStepKind.FALLBACK in kinds


def test_search_then_read_workspace_plan(planner: NaturalLanguagePlanner) -> None:
    workspace_plan = WorkspacePlan(
        tool_requests=(
            ToolRequest("file_read", {"action": "search_files", "keyword": "brain"}),
        ),
        workspace_operation="search_then_read",
        explanation_mode="search_then_read",
        files_considered=(),
        confidence=0.9,
        chain_after_search=True,
        search_query="brain",
    )
    analysis = _basic_analysis(
        message="Trouve et explique brain.py",
        tool_requests=list(workspace_plan.tool_requests),
        needs_tool=True,
    )
    analysis["workspace_plan"] = workspace_plan
    result = planner.plan("Trouve et explique brain.py", analysis)

    assert result.total_steps == 2
    assert result.execution_order[0] == "search"
    read_step = result.get_step("read")
    assert read_step is not None
    assert read_step.step_kind == PlanStepKind.CONDITIONAL
    assert read_step.dependencies == ("search",)


def test_task_execution_plan_import(planner: NaturalLanguagePlanner) -> None:
    task_plan = TaskExecutionPlan.from_definitions(
        "Search then read",
        (
            TaskStepDefinition(
                "search",
                "file_read",
                {"action": "search_files", "keyword": "titan"},
            ),
            TaskStepDefinition(
                "read",
                "file_read",
                {"action": "read_file", "path": "readme.txt"},
                depends_on=("search",),
                fallback_tool="web_search",
                fallback_inputs={"action": "search", "query": "titan readme"},
            ),
        ),
    )
    analysis = {"tool_requests": [], "task_execution_plan": task_plan}
    result = planner.plan("Search then read titan docs", analysis)

    assert result.total_steps == 2
    assert "file_read" in result.estimated_tools
    read_step = result.get_step("read")
    assert read_step is not None
    assert read_step.step_kind == PlanStepKind.FALLBACK


def test_requires_confirmation_for_delete(planner: NaturalLanguagePlanner) -> None:
    requests = [
        ToolRequest("obsidian", {"action": "delete_note", "path": "notes/old.md"}),
    ]
    analysis = _basic_analysis(
        message="Supprime notes/old.md",
        tool_requests=requests,
    )
    result = planner.plan("Supprime notes/old.md", analysis)

    assert result.requires_confirmation is True
    step = result.get_step("step_1")
    assert step is not None
    assert step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED


# ---------------------------------------------------------------------------
# P126-012 — to_tool_requests and orchestrate_plan integration
# ---------------------------------------------------------------------------


def test_to_tool_requests_skips_conditional_steps(planner: NaturalLanguagePlanner) -> None:
    workspace_plan = WorkspacePlan(
        tool_requests=(
            ToolRequest("file_read", {"action": "search_files", "keyword": "brain"}),
        ),
        workspace_operation="search_then_read",
        explanation_mode="search_then_read",
        files_considered=(),
        confidence=0.9,
        chain_after_search=True,
    )
    analysis = {
        "tool_requests": list(workspace_plan.tool_requests),
        "needs_tool": True,
        "workspace_plan": workspace_plan,
    }
    result = planner.plan("Trouve brain.py", analysis)
    requests = planner.to_tool_requests(result)

    assert len(requests) == 1
    assert requests[0].params.get("action") == "search_files"


def test_orchestrate_plan_executes_steps_in_order(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
    tool_manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    orchestrator = ToolOrchestrator(tool_manager)
    planner = NaturalLanguagePlanner()

    analysis = _basic_analysis(message="Quelle heure est-il ?")
    plan_result = planner.plan("Quelle heure est-il ?", analysis)
    results = orchestrator.orchestrate_plan(plan_result, message="Quelle heure est-il ?")

    assert len(results) == 1
    assert results[0].orchestration_status == OrchestrationStatus.COMPLETED
    assert results[0].selected_tool == "time"


def test_orchestrate_plan_runs_fallback_on_failure() -> None:
    tool_manager = MagicMock()
    tool_manager.runtime = None
    tool_manager.run = MagicMock(
        side_effect=[
            ToolResult(tool_name="file_read", success=False, error="not found"),
            ToolResult(tool_name="web_search", success=True, data="found"),
        ],
    )
    permission_manager = PermissionManager()
    orchestrator = ToolOrchestrator(tool_manager, permission_manager=permission_manager)

    step = PlanStep(
        step_id="primary",
        objective="Read",
        reasoning="Primary",
        required_tool="file_read",
        required_permission=PermissionLevel.AUTO_ALLOWED,
        expected_output="content",
        tool_params={"action": "read_file", "path": "missing.txt"},
        fallback_tool="web_search",
        fallback_params={"action": "search", "query": "missing"},
        selected_action="read_file",
    )
    plan = ExecutionPlan(
        overall_goal="Read or search",
        plan_summary="Fallback test",
        steps=(step,),
        execution_order=("primary",),
    )
    planner_result = PlannerResult.from_execution_plan(plan)
    results = orchestrator.orchestrate_plan(planner_result)

    assert len(results) == 2
    assert results[0].orchestration_status == OrchestrationStatus.FAILED
    assert results[1].selected_tool == "web_search"


def test_planner_result_from_dict_roundtrip() -> None:
    step = PlanStep(
        step_id="step_1",
        objective="obj",
        reasoning="why",
        required_tool="time",
        required_permission=PermissionLevel.AUTO_ALLOWED,
        expected_output="out",
    )
    plan = ExecutionPlan(
        overall_goal="goal",
        plan_summary="summary",
        steps=(step,),
        execution_order=("step_1",),
    )
    original = PlannerResult.from_execution_plan(plan)
    restored = PlannerResult.from_dict(original.to_dict())
    assert restored.overall_goal == original.overall_goal
    assert restored.total_steps == original.total_steps
    assert restored.execution_order == original.execution_order

# =====================================
# Titan Task Execution Engine Tests
# =====================================

"""Tests for Phase 12 Batch 3 — Multi-Step Task Execution Engine (P12B3-001–P12B3-006)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision import Intent, ToolDecisionEngine
from tools.decision.models import (
    ToolDecisionReport,
    enrich_task_execution_decision_context,
)
from tools.decision.task_execution_engine import (
    TaskExecutionEngine,
    extract_step_outputs,
    resolve_step_inputs,
)
from tools.decision.task_execution_models import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_STATUS_SKIPPED,
    TaskExecutionPlan,
    TaskExecutionStep,
    TaskStepDefinition,
)
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager
from tools.tool_result import ToolRequest, ToolResult


def _invoke_factory(responses: dict[str, ToolResult | list[ToolResult]]):
    """Build invoke fn keyed by tool name; lists rotate on repeated calls."""
    call_counts: dict[str, int] = {}

    def invoke(request: ToolRequest) -> ToolResult:
        key = request.tool_name
        spec = responses[key]
        if isinstance(spec, list):
            index = call_counts.get(key, 0)
            call_counts[key] = index + 1
            return spec[min(index, len(spec) - 1)]
        return spec

    return invoke


# ---------------------------------------------------------------------------
# P12B3-001 — TaskExecutionPlan
# ---------------------------------------------------------------------------


def test_task_execution_plan_from_definitions() -> None:
    steps = (
        TaskStepDefinition("search", "file_read", {"action": "search_files"}),
        TaskStepDefinition(
            "read",
            "file_read",
            {"action": "read_file", "path": "$search.metadata.search_results[0]"},
            depends_on=("search",),
        ),
    )
    plan = TaskExecutionPlan.from_definitions(
        "Find and read file",
        steps,
        expected_outputs=("summary",),
    )
    assert plan.objective == "Find and read file"
    assert len(plan.steps) == 2
    assert plan.dependencies["read"] == ("search",)
    assert "file_read" in plan.required_tools
    assert plan.expected_outputs == ("summary",)


# ---------------------------------------------------------------------------
# P12B3-002/004 — Engine: 2-step and 3-step
# ---------------------------------------------------------------------------


def test_two_step_task_output_chaining() -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Search then read",
        (
            TaskStepDefinition(
                "search",
                "file_read",
                {"action": "search_files", "keyword": "context"},
            ),
            TaskStepDefinition(
                "read",
                "file_read",
                {
                    "action": "read_file",
                    "path": "$search.metadata.search_results[0]",
                },
                depends_on=("search",),
            ),
        ),
    )
    invoke = _invoke_factory(
        {
            "file_read": [
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    data="found",
                    metadata={"search_results": ["Titan_Context.md"]},
                ),
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    data="# Titan context content",
                ),
            ],
        },
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)

    assert report.steps_completed == 2
    assert report.steps_failed == 0
    assert report.partial is False
    assert report.steps[1].inputs["path"] == "Titan_Context.md"
    assert "terminée avec succès" in report.execution_summary


def test_three_step_search_read_summary() -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Find Titan_Context.md, summarize it, then search TODOs",
        (
            TaskStepDefinition(
                "search",
                "file_read",
                {"action": "search_files", "pattern": "*Context*"},
            ),
            TaskStepDefinition(
                "read",
                "file_read",
                {
                    "action": "read_file",
                    "path": "$search.metadata.search_results[0]",
                },
                depends_on=("search",),
            ),
            TaskStepDefinition(
                "todo_search",
                "file_read",
                {
                    "action": "search_files",
                    "keyword": "TODO",
                    "context": "$read.data",
                },
                depends_on=("read",),
            ),
        ),
        expected_outputs=("final_report",),
    )
    invoke = _invoke_factory(
        {
            "file_read": [
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    metadata={"search_results": ["Titan_Context.md"]},
                ),
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    data="Line 1\nTODO: fix memory\nLine 3",
                ),
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    data="TODO: fix memory",
                    metadata={"search_results": ["brain/brain.py"]},
                ),
            ],
        },
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)

    assert report.steps_completed == 3
    assert report.steps_failed == 0
    assert report.steps[2].inputs["context"] == "Line 1\nTODO: fix memory\nLine 3"
    assert len(report.tool_results) == 3


# ---------------------------------------------------------------------------
# P12B3-005 — Failure, fallback, partial completion
# ---------------------------------------------------------------------------


def test_tool_failure_stops_with_partial_completion() -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Three steps with middle failure",
        (
            TaskStepDefinition("step1", "time", {}),
            TaskStepDefinition("step2", "web_search", {"query": "fail"}),
            TaskStepDefinition("step3", "time", {}),
        ),
    )
    invoke = _invoke_factory(
        {
            "time": ToolResult(tool_name="time", success=True, data="12:00"),
            "web_search": ToolResult(
                tool_name="web_search",
                success=False,
                error="API indisponible",
            ),
        },
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)

    assert report.steps_completed == 1
    assert report.steps_failed == 1
    assert report.partial is True
    assert report.steps[0].status == STEP_STATUS_COMPLETED
    assert report.steps[1].status == STEP_STATUS_FAILED
    assert report.steps[2].status == STEP_STATUS_SKIPPED
    assert "Travail restant" in report.execution_summary


def test_fallback_on_primary_failure() -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Search with fallback",
        (
            TaskStepDefinition(
                "search",
                "web_search",
                {"query": "Titan_Context.md"},
                fallback_tool="file_read",
                fallback_inputs={
                    "action": "search_files",
                    "pattern": "*Context*",
                },
            ),
            TaskStepDefinition(
                "read",
                "file_read",
                {
                    "action": "read_file",
                    "path": "$search.metadata.search_results[0]",
                },
                depends_on=("search",),
            ),
        ),
    )
    invoke = _invoke_factory(
        {
            "web_search": ToolResult(
                tool_name="web_search",
                success=False,
                error="offline",
            ),
            "file_read": [
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    metadata={"search_results": ["Titan_Context.md"]},
                ),
                ToolResult(
                    tool_name="file_read",
                    success=True,
                    data="summary content",
                ),
            ],
        },
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)

    assert report.steps_completed == 2
    assert report.steps_failed == 0
    assert report.steps[0].tool == "file_read"
    assert report.steps[0].outputs.get("fallback_used") is True


def test_unmet_dependency_marks_failure() -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Read without search",
        (
            TaskStepDefinition(
                "read",
                "file_read",
                {"action": "read_file", "path": "missing.md"},
                depends_on=("search",),
            ),
        ),
    )
    invoke = _invoke_factory(
        {
            "file_read": ToolResult(
                tool_name="file_read",
                success=True,
                data="unused",
            ),
        },
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)

    assert report.steps_completed == 0
    assert report.steps_failed == 1
    assert report.steps[0].status == STEP_STATUS_FAILED
    assert "Dépendances" in (report.steps[0].failure_reason or "")


# ---------------------------------------------------------------------------
# P12B3-003/004 — Step model and input resolution
# ---------------------------------------------------------------------------


def test_step_record_fields() -> None:
    step = TaskExecutionStep(
        step_id="search",
        tool="file_read",
        status=STEP_STATUS_COMPLETED,
        started_at="2026-07-02T10:00:00+00:00",
        finished_at="2026-07-02T10:00:01+00:00",
        duration_ms=1000.0,
        inputs={"action": "search_files"},
        outputs={"success": True, "data": "ok"},
        failure_reason=None,
    )
    restored = TaskExecutionStep.from_dict(step.to_dict())
    assert restored.step_id == "search"
    assert restored.duration_ms == 1000.0


def test_resolve_step_inputs_placeholder() -> None:
    context = {
        "search": {
            "success": True,
            "metadata": {"search_results": ["a.md", "b.md"]},
            "search_results": ["a.md", "b.md"],
        },
    }
    resolved = resolve_step_inputs(
        {"path": "$search.metadata.search_results[0]", "static": "value"},
        context,
    )
    assert resolved["path"] == "a.md"
    assert resolved["static"] == "value"


def test_extract_step_outputs_flattens_metadata() -> None:
    result = ToolResult(
        tool_name="file_read",
        success=True,
        data="content",
        metadata={"search_results": ["x.md"]},
    )
    outputs = extract_step_outputs(result)
    assert outputs["data"] == "content"
    assert outputs["search_results"] == ["x.md"]


# ---------------------------------------------------------------------------
# P12B3-006 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_multi_step_enrichment() -> None:
    base = ToolDecisionReport(
        intent=Intent.WORKSPACE_EXPLAIN,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="file_read",
        decision_reason="multi-step",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    invoke = _invoke_factory(
        {
            "time": ToolResult(tool_name="time", success=True, data="now"),
        },
    )
    plan = TaskExecutionPlan.from_definitions(
        "Quick task",
        (TaskStepDefinition("t1", "time", {}),),
    )
    report = TaskExecutionEngine().execute(plan, invoke=invoke)
    enriched = enrich_task_execution_decision_context(base, report)

    assert enriched.multi_step_execution is True
    assert enriched.steps_completed == 1
    assert enriched.steps_failed == 0
    assert enriched.total_duration is not None
    assert enriched.execution_summary
    assert enriched.task_execution_result is not None
    assert enriched.explanation_mode == "multi_step_execution"

    serialized = enriched.to_dict()
    assert serialized["multi_step_execution"] is True
    assert serialized["steps_completed"] == 1


def test_decision_report_from_dict_legacy_defaults() -> None:
    data = {
        "intent": "unknown",
        "confidence": 0.5,
        "tool_required": False,
        "candidate_tools": [],
        "selected_tool": None,
        "decision_reason": "legacy",
        "risk_level": "safe",
        "confirmation_required": False,
    }
    report = ToolDecisionReport.from_dict(data)
    assert report.multi_step_execution is False
    assert report.steps_completed == 0
    assert report.steps_failed == 0
    assert report.total_duration is None
    assert report.execution_summary == ""
    assert report.task_execution_result is None


# ---------------------------------------------------------------------------
# Coordinator integration
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "titan_project"
    root.mkdir()
    target = root / "Titan_Context.md"
    target.write_text("# Context\nTODO: item one\n", encoding="utf-8")
    return root


@pytest.fixture
def coordinator(project_root: Path) -> ExecutionCoordinator:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=MagicMock())
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    reasoning = Reasoning(project_root=project_root)
    coord = ExecutionCoordinator(orchestrator, dispatcher, reasoning=reasoning)
    return coord


def test_coordinator_runs_multi_step_plan(monkeypatch, coordinator: ExecutionCoordinator) -> None:
    plan = TaskExecutionPlan.from_definitions(
        "Search and read context",
        (
            TaskStepDefinition(
                "search",
                "file_read",
                {"action": "search_files", "pattern": "*Context*"},
            ),
            TaskStepDefinition(
                "read",
                "file_read",
                {
                    "action": "read_file",
                    "path": "$search.metadata.search_results[0]",
                },
                depends_on=("search",),
            ),
        ),
    )

    def fake_analyze(message, availability_resolver=None):
        base = ToolDecisionEngine().decide(message)
        return {
            "message": message,
            "goal": plan.objective,
            "needs_memory": False,
            "needs_tool": True,
            "needs_clarification": False,
            "tool_requests": [],
            "decision_report": base,
            "fallback_action": base.fallback_action.value,
            "task_execution_plan": plan,
        }

    monkeypatch.setattr(coordinator.reasoning, "analyze", fake_analyze)
    result = coordinator.execute("run multi step")

    assert result.decision_report is not None
    assert result.decision_report.multi_step_execution is True
    assert result.decision_report.steps_completed == 2
    assert "Objectif" in result.tool_results_text


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_regression_patch_decision_report_fields() -> None:
    data = {
        "intent": "workspace_modify",
        "confidence": 0.9,
        "tool_required": False,
        "candidate_tools": [],
        "selected_tool": None,
        "decision_reason": "patch",
        "risk_level": "medium",
        "confirmation_required": True,
        "patch_application_requested": True,
        "rollback_available": True,
    }
    report = ToolDecisionReport.from_dict(data)
    assert report.patch_application_requested is True
    assert report.multi_step_execution is False


def test_regression_rollback_decision_report_fields() -> None:
    data = {
        "intent": "unknown",
        "confidence": 0.5,
        "tool_required": False,
        "candidate_tools": [],
        "selected_tool": None,
        "decision_reason": "rollback",
        "risk_level": "safe",
        "confirmation_required": False,
        "rollback_applied": True,
        "rollback_id": "rb-1",
    }
    report = ToolDecisionReport.from_dict(data)
    assert report.rollback_applied is True
    assert report.multi_step_execution is False


def test_regression_workspace_decide(engine_decision: ToolDecisionEngine) -> None:
    report = engine_decision.decide("Explique config/settings.py")
    assert report.intent == Intent.WORKSPACE_EXPLAIN
    assert report.multi_step_execution is False


@pytest.fixture
def engine_decision() -> ToolDecisionEngine:
    return ToolDecisionEngine()

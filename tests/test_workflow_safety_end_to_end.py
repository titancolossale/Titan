# =====================================
# Titan Workflow Safety E2E Tests
# =====================================

"""End-to-end safety validation: confirmation gates, failures, cancellation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain.brain import Brain
from brain.cognitive_models import (
    CognitivePlan,
    CognitivePhase,
    PlanRuntimeState,
    PlanStatus,
    PlanVerificationResult,
    TaskGraph,
    TaskGraphNode,
)
from brain.cognitive_operating_system import ExecutionStatus
from brain.autonomous_workflow_engine import WorkflowStatus
from tools.planner_models import ExecutionPlan, PlannerResult, PlanStepKind


def _planner_result() -> PlannerResult:
    execution_plan = ExecutionPlan(
        overall_goal="Safety test",
        plan_summary="",
        steps=(),
        execution_order=(),
    )
    return PlannerResult(
        overall_goal="Safety test",
        plan_summary="",
        total_steps=1,
        estimated_tools=(),
        requires_confirmation=True,
        execution_order=("node_1",),
        steps=(),
        plan=execution_plan,
    )


def _risky_cognitive_plan(*, requires_confirmation: bool = True) -> CognitivePlan:
    node = TaskGraphNode(
        node_id="node_1",
        objective="Delete all notes",
        tool="obsidian",
        dependencies=(),
        cognitive_phase=CognitivePhase.PLANNING,
        step_kind=PlanStepKind.STANDARD,
    )
    return CognitivePlan(
        plan_id="plan_risky",
        message="Delete all notes",
        task_graph=TaskGraph(nodes=(node,), execution_order=("node_1",)),
        planner_result=_planner_result(),
        execution_plan=_planner_result().plan,
        analysis={},
        requires_confirmation=requires_confirmation,
        clarification_required=False,
    )


@pytest.fixture
def safety_brain(brain: Brain) -> Brain:
    return brain


# ---------------------------------------------------------------------------
# Confirmation gate guarantees
# ---------------------------------------------------------------------------


def test_confirmation_gate_blocks_without_user_approval(safety_brain: Brain) -> None:
    """Plans requiring confirmation must not execute without confirmed=True."""
    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator
    orchestrator.create_plan = lambda message: _risky_cognitive_plan()  # type: ignore[method-assign]

    plan = safety_brain.build_cognitive_execution_plan("Delete all notes")
    result = safety_brain.execute_cognitive_plan(plan.plan_id, confirmed=False)

    assert result.success is False
    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert "confirmation" in result.message.lower()


def test_confirmation_gate_cannot_bypass_meta_clarification_without_confirmed(
    safety_brain: Brain,
) -> None:
    """Meta-cognition clarification blocks execution even when plan is auto-allowed."""
    result = safety_brain.run_cognitive_cycle("Fix it", confirmed=False)

    assert result.success is False
    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION


def test_confirmation_gate_allows_execution_when_confirmed(safety_brain: Brain) -> None:
    """confirmed=True must pass meta-cognition and plan confirmation gates."""
    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator
    original_create = orchestrator.create_plan

    def _create_with_confirmation(message: str) -> CognitivePlan:
        plan = original_create(message)
        return CognitivePlan(
            plan_id=plan.plan_id,
            message=plan.message,
            task_graph=plan.task_graph,
            planner_result=plan.planner_result,
            execution_plan=plan.execution_plan,
            analysis=plan.analysis,
            requires_confirmation=True,
            clarification_required=False,
        )

    with patch.object(orchestrator, "create_plan", side_effect=_create_with_confirmation):
        result = safety_brain.run_cognitive_cycle("What time is it?", confirmed=True)

    assert result.execution.status in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
    }


def test_workflow_confirmation_gate_blocks_execution(safety_brain: Brain) -> None:
    """AWE must not call execute_plan when confirmation is required."""
    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator

    with patch.object(
        orchestrator,
        "create_plan",
        return_value=_risky_cognitive_plan(),
    ), patch.object(orchestrator, "execute_plan") as mock_execute:
        record = safety_brain.create_workflow("Delete all notes")
        result = safety_brain.start_workflow(record.workflow_id, confirmed=False)

    assert result.success is False
    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    mock_execute.assert_not_called()


# ---------------------------------------------------------------------------
# Failure handling — no silent failures
# ---------------------------------------------------------------------------


def test_workflow_failure_records_status_and_trace(safety_brain: Brain) -> None:
    """Failed verification must set FAILED status and preserve exportable trace."""
    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator

    with patch.object(
        orchestrator,
        "verify_plan",
        return_value=PlanVerificationResult(
            passed=False,
            summary="Integration safety failure",
            failed_node_ids=("node_1",),
        ),
    ):
        record = safety_brain.create_workflow("Task that will fail verification")
        result = safety_brain.start_workflow(record.workflow_id)

    assert result.success is False
    assert result.workflow.status == WorkflowStatus.FAILED
    assert result.workflow.error_message == "Integration safety failure"
    assert result.workflow.learning_recorded is True

    exported = safety_brain.export_workflow(record.workflow_id)
    assert exported["status"] == WorkflowStatus.FAILED.value
    assert exported.get("error_message") == "Integration safety failure"


def test_cos_failure_generates_learning_candidate(safety_brain: Brain) -> None:
    """COS failed executions must invoke Knowledge Learning Engine."""
    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator
    runtime = PlanRuntimeState(plan_id="plan_fail", status=PlanStatus.FAILED)

    with patch.object(orchestrator, "execute_plan", return_value=runtime), patch.object(
        orchestrator,
        "verify_plan",
        return_value=PlanVerificationResult(
            passed=False,
            summary="Execution node failed",
            failed_node_ids=("node_0",),
        ),
    ), patch.object(
        safety_brain.knowledge_learning_engine,
        "learn_from_execution",
    ) as mock_learn:
        mock_learn.return_value = safety_brain.knowledge_learning_engine.learn_from_execution(
            tool_name="time",
            success=False,
            summary_message="Execution node failed",
        )
        result = safety_brain.run_cognitive_cycle("What time is it?")

    assert result.execution.status == ExecutionStatus.FAILED
    assert result.execution.learning_recorded is True
    assert mock_learn.call_count >= 1
    failure_calls = [c for c in mock_learn.call_args_list if c.kwargs.get("success") is False]
    assert failure_calls


# ---------------------------------------------------------------------------
# Cancellation — no further tool calls
# ---------------------------------------------------------------------------


def test_cancel_cognitive_execution_prevents_re_execution(safety_brain: Brain) -> None:
    """Cancelled COS executions must reject subsequent execute_plan calls."""
    plan = safety_brain.build_cognitive_execution_plan("Cancel safety test")
    safety_brain.cancel_cognitive_execution(plan.execution_id)

    result = safety_brain.execute_cognitive_plan(plan.plan_id)

    assert result.success is False
    assert "terminal" in result.message.lower()


def test_cancel_workflow_invokes_orchestrator_cancel(safety_brain: Brain) -> None:
    """Workflow cancel must stop the underlying cognitive plan."""
    record = safety_brain.create_workflow("Cancel workflow safety test")
    record.plan_id = "plan_wf_cancel"
    safety_brain.autonomous_workflow_engine._workflows[record.workflow_id] = record

    orchestrator = safety_brain.execution_coordinator.cognitive_orchestrator
    with patch.object(orchestrator, "cancel_plan") as mock_cancel:
        cancelled = safety_brain.cancel_workflow(record.workflow_id)

    assert cancelled is not None
    assert cancelled.status == WorkflowStatus.CANCELLED
    mock_cancel.assert_called_once_with("plan_wf_cancel")

    restart = safety_brain.start_workflow(record.workflow_id)
    assert restart.success is False
    assert "terminal" in restart.message.lower()


def test_execution_trace_contains_all_lifecycle_stages(safety_brain: Brain) -> None:
    """Successful COS runs must record confirm → execute → learn → complete in trace."""
    result = safety_brain.run_cognitive_cycle("What time is it?")
    exported = safety_brain.export_cognitive_execution(result.execution.execution_id)
    stages = [entry["stage"] for entry in exported["trace"]["entries"]]

    for stage in ("confirm", "execute", "learn", "complete"):
        assert stage in stages

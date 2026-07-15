# =====================================
# Titan Cognitive Lifecycle E2E Tests
# =====================================

"""End-to-end validation of the six official cognitive request flows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain.brain import Brain
from brain.cognitive_models import PlanVerificationResult
from brain.cognitive_operating_system import CognitiveStage, ExecutionStatus
from brain.natural_language_orchestrator import DetectedIntent, SystemName


def _write(path: Path, content: str = "# note\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path) -> Path:
    project = root / "LifecycleProject"
    project.mkdir(parents=True)
    _write(project / "README.md", "# LifecycleProject\n")
    for pkg in ("core", "brain", "tests"):
        (project / pkg).mkdir(exist_ok=True)
        _write(project / pkg / "__init__.py", "")
    _write(
        project / "brain" / "service.py",
        "class Service:\n    def run(self):\n        return True\n",
    )
    _write(project / "docs" / "ARCHITECTURE.md", "# Architecture\n")
    return project


@pytest.fixture
def lifecycle_brain(brain: Brain, tmp_path: Path) -> Brain:
    project = _make_python_project(tmp_path)
    brain.tool_manager._project_root = project  # type: ignore[attr-defined]
    return brain


# ---------------------------------------------------------------------------
# Flow 1 — Simple informational request
# ---------------------------------------------------------------------------


def test_flow1_simple_informational_via_nlo(lifecycle_brain: Brain) -> None:
    """Request → NLO → Reasoning → Brain systems → response."""
    result = lifecycle_brain.process_request("What is the capital of France?")

    assert result.detected_intent == DetectedIntent.QUESTION
    assert SystemName.REASONING_ENGINE.value in result.systems_used.invoked
    assert result.confidence > 0.0
    assert result.final_response


def test_flow1_simple_informational_via_cognitive_cycle(lifecycle_brain: Brain) -> None:
    """Request → COS → context → reason → evaluate → plan → execute → learn."""
    result = lifecycle_brain.run_cognitive_cycle("What time is it?")

    assert result.success is True
    assert result.execution.status == ExecutionStatus.COMPLETED
    assert result.execution.learning_recorded is True

    trace = lifecycle_brain.get_cognitive_execution_trace(result.execution.execution_id)
    stages = [entry.stage for entry in trace.entries]

    for expected in (
        CognitiveStage.RECEIVE,
        CognitiveStage.CONTEXT,
        CognitiveStage.REASON,
        CognitiveStage.EVALUATE,
        CognitiveStage.PLAN,
        CognitiveStage.CONFIRM,
        CognitiveStage.EXECUTE,
        CognitiveStage.LEARN,
        CognitiveStage.COMPLETE,
    ):
        assert expected in stages


# ---------------------------------------------------------------------------
# Flow 2 — Ambiguous request → clarification, no execution
# ---------------------------------------------------------------------------


def test_flow2_ambiguous_request_blocks_execution(lifecycle_brain: Brain) -> None:
    """Short/vague requests must stop at confirmation — no tool execution."""
    result = lifecycle_brain.run_cognitive_cycle("Fix it")

    assert result.success is False
    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert "open questions" in result.message.lower() or "clarification" in result.message.lower()

    trace = lifecycle_brain.get_cognitive_execution_trace(result.execution.execution_id)
    stage_names = {entry.stage for entry in trace.entries}
    assert CognitiveStage.EXECUTE not in stage_names


# ---------------------------------------------------------------------------
# Flow 3 — Multi-step workflow request
# ---------------------------------------------------------------------------


def test_flow3_multi_step_workflow_via_cos(lifecycle_brain: Brain) -> None:
    """COS may delegate to Autonomous Workflow Engine for multi-step objectives."""
    result = lifecycle_brain.run_cognitive_cycle(
        "Plan integration tests, run pytest, and summarize the results",
        use_workflow_engine=True,
    )

    assert result.execution.status in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.AWAITING_CONFIRMATION,
        ExecutionStatus.FAILED,
    }
    metrics = lifecycle_brain.get_cognitive_execution_metrics(result.execution.execution_id)
    assert metrics.subsystem_calls.get("reasoning_engine", 0) >= 1
    assert metrics.subsystem_calls.get("cognitive_context_builder", 0) >= 1


def test_flow3_workflow_engine_lifecycle(lifecycle_brain: Brain) -> None:
    """Workflow create → start must produce traceable artifacts."""
    record = lifecycle_brain.create_workflow("Run tests and summarize outcomes")
    run = lifecycle_brain.start_workflow(record.workflow_id)

    assert run.workflow.workflow_id == record.workflow_id
    exported = lifecycle_brain.export_workflow(record.workflow_id)
    assert "artifacts" in exported
    assert exported["status"] in {
        "completed",
        "awaiting_confirmation",
        "failed",
    }


# ---------------------------------------------------------------------------
# Flow 4 — Project-aware request
# ---------------------------------------------------------------------------


def test_flow4_project_aware_via_nlo(lifecycle_brain: Brain) -> None:
    """Project analysis intents route through Project Intelligence path."""
    result = lifecycle_brain.process_request("Analyze the project architecture")

    assert result.detected_intent in {
        DetectedIntent.PROJECT_ANALYSIS,
        DetectedIntent.ARCHITECTURE,
    }
    assert SystemName.REASONING_ENGINE.value in result.systems_used.invoked


def test_flow4_project_aware_cos_includes_world_model(lifecycle_brain: Brain) -> None:
    """COS context stage must assemble World Model for project requests."""
    plan = lifecycle_brain.build_cognitive_execution_plan("Analyze project structure")
    metrics = lifecycle_brain.get_cognitive_execution_metrics(plan.execution_id)

    assert metrics.subsystem_calls.get("world_model", 0) >= 1
    assert metrics.subsystem_calls.get("cognitive_context_builder", 0) >= 1
    exported = lifecycle_brain.export_cognitive_execution(plan.execution_id)
    assert "world_snapshot" in exported.get("artifacts", {}) or "plan" in exported


# ---------------------------------------------------------------------------
# Flow 5 — Failed execution
# ---------------------------------------------------------------------------


def test_flow5_failed_execution_captures_trace_and_learning(lifecycle_brain: Brain) -> None:
    """Verification failure → FAILED status, trace preserved, learning recorded."""
    orchestrator = lifecycle_brain.execution_coordinator.cognitive_orchestrator

    with patch.object(
        orchestrator,
        "verify_plan",
        return_value=PlanVerificationResult(
            passed=False,
            summary="Step failed during integration validation",
            failed_node_ids=("node_0",),
        ),
    ):
        result = lifecycle_brain.run_cognitive_cycle("What time is it?")

    assert result.success is False
    assert result.execution.status == ExecutionStatus.FAILED
    assert result.execution.learning_recorded is True
    assert result.execution.error_message or result.message

    exported = lifecycle_brain.export_cognitive_execution(result.execution.execution_id)
    assert exported["status"] == ExecutionStatus.FAILED.value
    assert len(exported.get("trace", {}).get("entries", [])) >= 5


# ---------------------------------------------------------------------------
# Flow 6 — Cancelled execution
# ---------------------------------------------------------------------------


def test_flow6_cancelled_execution_persists_state(lifecycle_brain: Brain) -> None:
    """Cancel must stop work and persist CANCELLED — no further execution."""
    plan = lifecycle_brain.build_cognitive_execution_plan("Task to cancel")
    cancelled = lifecycle_brain.cancel_cognitive_execution(plan.execution_id)

    assert cancelled is not None
    assert cancelled.status == ExecutionStatus.CANCELLED

    record = lifecycle_brain.get_cognitive_execution(plan.execution_id)
    assert record is not None
    assert record.status == ExecutionStatus.CANCELLED

    second_cancel = lifecycle_brain.cancel_cognitive_execution(plan.execution_id)
    assert second_cancel is None


def test_flow6_cancel_workflow_stops_orchestrator(lifecycle_brain: Brain) -> None:
    """Workflow cancel must invoke cognitive orchestrator cancel_plan."""
    record = lifecycle_brain.create_workflow("Workflow to cancel")
    record.plan_id = "plan_cancel_test"
    lifecycle_brain.autonomous_workflow_engine._workflows[record.workflow_id] = record

    orchestrator = lifecycle_brain.execution_coordinator.cognitive_orchestrator
    with patch.object(orchestrator, "cancel_plan") as mock_cancel:
        cancelled = lifecycle_brain.cancel_workflow(record.workflow_id)

    assert cancelled is not None
    assert cancelled.status.value == "cancelled"
    mock_cancel.assert_called_once_with("plan_cancel_test")

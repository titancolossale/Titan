# =====================================
# Titan Autonomous Workflow Engine Tests
# =====================================

"""Comprehensive tests for Autonomous Workflow Engine V1."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.autonomous_workflow_engine import (
    AutonomousWorkflowEngine,
    WorkflowStatus,
)
from brain.cognitive_context_builder import CognitiveContext
from brain.cognitive_models import (
    CognitivePhase,
    CognitivePlan,
    PlanRuntimeState,
    PlanStatus,
    PlanVerificationResult,
    TaskGraph,
    TaskGraphNode,
)
from brain.executive_function import ExecutiveEvaluation, FocusRecommendation
from brain.knowledge_learning_engine import KnowledgeSource, LearningResult
from brain.meta_cognition import (
    HallucinationRisk,
    MetaCognitionRecommendation,
    MetaCognitionReport,
    ReasoningQuality,
    RecommendationStrength,
)
from brain.reasoning_models import (
    ReasoningDomain,
    ReasoningQuestion,
    ReasoningRecommendation,
    ReasoningResult,
    ReasoningSummary,
    ReasoningUrgency,
    RequestUnderstanding,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from tools.planner_models import ExecutionPlan, PlannerResult, PlanStepKind


def _reasoning_result(
    message: str = "Test objective",
    *,
    open_questions: tuple[ReasoningQuestion, ...] = (),
) -> ReasoningResult:
    understanding = RequestUnderstanding(
        objective=message,
        constraints=(),
        urgency=ReasoningUrgency.NORMAL,
        domain=ReasoningDomain.GENERAL,
        requested_output="answer",
        raw_message=message,
    )
    summary = ReasoningSummary(
        objective=message,
        domain=ReasoningDomain.GENERAL,
        urgency=ReasoningUrgency.NORMAL,
        requested_output="answer",
        constraints=(),
        confidence_score=0.85,
        reasoning_quality_score=0.8,
        completeness_score=0.8,
        clarification_required=False,
        headline=message,
    )
    return ReasoningResult(
        message=message,
        understanding=understanding,
        summary=summary,
        steps=(),
        alternatives=(),
        risks=(),
        assumptions=(),
        open_questions=open_questions,
        recommendation=ReasoningRecommendation(
            strategy="Proceed with plan",
            supporting_arguments=("Clear objective",),
            confidence=0.85,
        ),
    )


def _meta_report(
    *,
    confidence: float = 0.9,
    clarification_required: bool = False,
) -> MetaCognitionReport:
    return MetaCognitionReport(
        id="meta_test",
        evaluation_target="reasoning",
        confidence_score=confidence,
        uncertainty_score=0.1,
        ambiguity_score=0.1,
        missing_information=(),
        assumptions=(),
        conflicting_evidence=(),
        hallucination_risk=HallucinationRisk.LOW,
        clarification_required=clarification_required,
        reasoning_quality=ReasoningQuality.GOOD,
        recommendation=MetaCognitionRecommendation(
            strength=RecommendationStrength.STRONG,
            summary="Proceed",
            proceed=True,
        ),
    )


def _executive_evaluation() -> ExecutiveEvaluation:
    return ExecutiveEvaluation(
        current_mission=None,
        ranked_missions=(),
        recommendation=FocusRecommendation(
            recommended_mission_id=None,
            recommended_title=None,
            current_mission_id=None,
            should_switch=False,
            reasoning="No active missions",
            priority_score=0.0,
        ),
        reasoning="No missions ranked",
        blocked_missions=(),
        idle_missions=(),
        workspace_summary="",
    )


def _cognitive_context() -> CognitiveContext:
    mock = MagicMock(spec=CognitiveContext)
    mock.to_dict.return_value = {"summary": "Test context"}
    return mock


def _planner_result() -> PlannerResult:
    execution_plan = ExecutionPlan(
        overall_goal="Test",
        plan_summary="",
        steps=(),
        execution_order=(),
    )
    return PlannerResult(
        overall_goal="Test",
        plan_summary="",
        total_steps=0,
        estimated_tools=(),
        requires_confirmation=False,
        execution_order=(),
        steps=(),
        plan=execution_plan,
    )


def _cognitive_plan(
    *,
    plan_id: str = "plan_test",
    requires_confirmation: bool = False,
    clarification_required: bool = False,
    tool: str = "time",
) -> CognitivePlan:
    node = TaskGraphNode(
        node_id="node_1",
        objective="Run time tool",
        tool=tool,
        dependencies=(),
        cognitive_phase=CognitivePhase.PLANNING,
        step_kind=PlanStepKind.STANDARD,
    )
    return CognitivePlan(
        plan_id=plan_id,
        message="Test",
        task_graph=TaskGraph(nodes=(node,), execution_order=("node_1",)),
        planner_result=_planner_result(),
        execution_plan=_planner_result().plan,
        analysis={},
        requires_confirmation=requires_confirmation,
        clarification_required=clarification_required,
    )


@pytest.fixture
def context_manager(tmp_path: Path) -> ContextManager:
    state = StateManager(file_path=tmp_path / "state.json")
    mission = MissionManager(file_path=tmp_path / "mission.json")
    return ContextManager(state_manager=state, mission_manager=mission)


@pytest.fixture
def workflow_engine(context_manager: ContextManager) -> AutonomousWorkflowEngine:
    reasoning_engine = MagicMock()
    context_builder = MagicMock()
    executive_function = MagicMock()
    meta_cognition = MagicMock()
    knowledge_learning = MagicMock()
    cognitive_orchestrator = MagicMock()

    context_builder.build_for_request.return_value = _cognitive_context()
    reasoning_engine.reason.return_value = _reasoning_result()
    executive_function.evaluate_missions.return_value = _executive_evaluation()
    meta_cognition.evaluate_reasoning.return_value = _meta_report()
    meta_cognition.requires_clarification.return_value = False
    meta_cognition.confidence.return_value = 0.9

    plan = _cognitive_plan()
    runtime = PlanRuntimeState(plan_id=plan.plan_id, status=PlanStatus.COMPLETED)
    cognitive_orchestrator.create_plan.return_value = plan
    cognitive_orchestrator.execute_plan.return_value = runtime
    cognitive_orchestrator.verify_plan.return_value = PlanVerificationResult(
        passed=True,
        summary="All steps completed",
    )

    knowledge_learning.learn_from_execution.return_value = LearningResult(
        source=KnowledgeSource.EXECUTION,
        candidates_created=(),
        candidates_updated=(),
        patterns_detected=0,
        message="Recorded",
    )
    knowledge_learning.learn_from_reasoning.return_value = LearningResult(
        source=KnowledgeSource.REASONING,
        candidates_created=(),
        candidates_updated=(),
        patterns_detected=0,
        message="Recorded reasoning",
    )

    return AutonomousWorkflowEngine(
        reasoning_engine=reasoning_engine,
        cognitive_context_builder=context_builder,
        executive_function=executive_function,
        meta_cognition=meta_cognition,
        knowledge_learning_engine=knowledge_learning,
        cognitive_orchestrator=cognitive_orchestrator,
        context_manager=context_manager,
    )


def test_create_workflow(workflow_engine: AutonomousWorkflowEngine) -> None:
    record = workflow_engine.create_workflow("Research FastAPI middleware")

    assert record.workflow_id.startswith("wf_")
    assert record.objective == "Research FastAPI middleware"
    assert record.status == WorkflowStatus.CREATED
    assert record.user == "Nolan"


def test_create_workflow_rejects_empty_objective(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    with pytest.raises(ValueError, match="objective"):
        workflow_engine.create_workflow("   ")


def test_start_workflow_completes_successfully(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    record = workflow_engine.create_workflow("What time is it?")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.success is True
    assert result.workflow.status == WorkflowStatus.COMPLETED
    assert result.execution is not None
    assert result.workflow.learning_recorded is True
    workflow_engine._knowledge_learning_engine.learn_from_execution.assert_called_once()
    workflow_engine._knowledge_learning_engine.learn_from_reasoning.assert_called_once()


def test_start_workflow_awaits_meta_cognition_clarification(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._meta_cognition.requires_clarification.return_value = True
    workflow_engine._meta_cognition.evaluate_reasoning.return_value = _meta_report(
        clarification_required=True,
    )

    record = workflow_engine.create_workflow("Ambiguous request")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.success is False
    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    assert "clarification" in result.message.lower()
    workflow_engine._cognitive_orchestrator.create_plan.assert_not_called()


def test_start_workflow_awaits_low_confidence(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._meta_cognition.confidence.return_value = 0.2
    workflow_engine._meta_cognition.evaluate_reasoning.return_value = _meta_report(
        confidence=0.2,
    )

    record = workflow_engine.create_workflow("Uncertain task")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    assert "confidence" in result.message.lower()


def test_start_workflow_awaits_open_questions(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._reasoning_engine.reason.return_value = _reasoning_result(
        open_questions=(
            ReasoningQuestion(
                id="q1",
                question="Which file should be edited?",
                importance=0.9,
            ),
        ),
    )

    record = workflow_engine.create_workflow("Edit the file")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    assert "open questions" in result.message.lower()


def test_start_workflow_awaits_plan_confirmation(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._cognitive_orchestrator.create_plan.return_value = _cognitive_plan(
        requires_confirmation=True,
    )

    record = workflow_engine.create_workflow("Delete all notes")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    assert "confirmation" in result.message.lower()
    workflow_engine._cognitive_orchestrator.execute_plan.assert_not_called()


def test_start_workflow_confirmed_skips_confirmation_gate(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._meta_cognition.requires_clarification.return_value = True
    workflow_engine._cognitive_orchestrator.create_plan.return_value = _cognitive_plan(
        requires_confirmation=True,
    )

    record = workflow_engine.create_workflow("Risky but approved task")
    result = workflow_engine.start_workflow(record.workflow_id, confirmed=True)

    assert result.success is True
    assert result.workflow.status == WorkflowStatus.COMPLETED
    workflow_engine._cognitive_orchestrator.execute_plan.assert_called_once()


def test_start_workflow_fails_verification(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    workflow_engine._cognitive_orchestrator.verify_plan.return_value = PlanVerificationResult(
        passed=False,
        summary="Step failed",
        failed_node_ids=("node_1",),
    )

    record = workflow_engine.create_workflow("Failing task")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.success is False
    assert result.workflow.status == WorkflowStatus.FAILED
    assert result.workflow.error_message == "Step failed"


def test_start_workflow_suspended_execution(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    plan = _cognitive_plan()
    runtime = PlanRuntimeState(plan_id=plan.plan_id, status=PlanStatus.SUSPENDED)
    workflow_engine._cognitive_orchestrator.create_plan.return_value = plan
    workflow_engine._cognitive_orchestrator.execute_plan.return_value = runtime

    record = workflow_engine.create_workflow("Needs tool confirmation")
    result = workflow_engine.start_workflow(record.workflow_id)

    assert result.workflow.status == WorkflowStatus.AWAITING_CONFIRMATION
    assert "confirmation" in result.message.lower()


def test_pause_and_resume_workflow(workflow_engine: AutonomousWorkflowEngine) -> None:
    record = workflow_engine.create_workflow("Pausable task")
    paused = workflow_engine.pause_workflow(record.workflow_id)

    assert paused is not None
    assert paused.status == WorkflowStatus.PAUSED
    assert paused.paused_from == WorkflowStatus.CREATED

    result = workflow_engine.resume_workflow(record.workflow_id)
    assert result.workflow.status == WorkflowStatus.COMPLETED


def test_pause_executing_workflow_cancels_plan(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    record = workflow_engine.create_workflow("Running task")
    record.status = WorkflowStatus.EXECUTING
    record.plan_id = "plan_active"

    paused = workflow_engine.pause_workflow(record.workflow_id)

    assert paused is not None
    assert paused.status == WorkflowStatus.PAUSED
    workflow_engine._cognitive_orchestrator.cancel_plan.assert_called_once_with("plan_active")


def test_cancel_workflow(workflow_engine: AutonomousWorkflowEngine) -> None:
    record = workflow_engine.create_workflow("Cancel me")
    record.plan_id = "plan_cancel"

    cancelled = workflow_engine.cancel_workflow(record.workflow_id)

    assert cancelled is not None
    assert cancelled.status == WorkflowStatus.CANCELLED
    workflow_engine._cognitive_orchestrator.cancel_plan.assert_called_once_with("plan_cancel")


def test_cancel_terminal_workflow_returns_none(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    record = workflow_engine.create_workflow("Done")
    record.status = WorkflowStatus.COMPLETED

    assert workflow_engine.cancel_workflow(record.workflow_id) is None


def test_get_and_list_workflows(workflow_engine: AutonomousWorkflowEngine) -> None:
    first = workflow_engine.create_workflow("First")
    second = workflow_engine.create_workflow("Second")

    assert workflow_engine.get_workflow(first.workflow_id) is first
    assert len(workflow_engine.list_workflows()) == 2

    created_only = workflow_engine.list_workflows(status=WorkflowStatus.CREATED)
    assert len(created_only) == 2
    assert {item.workflow_id for item in created_only} == {
        first.workflow_id,
        second.workflow_id,
    }


def test_export_workflow_includes_artifacts(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    record = workflow_engine.create_workflow("Export test")
    workflow_engine.start_workflow(record.workflow_id)

    exported = workflow_engine.export_workflow(record.workflow_id)

    assert exported["workflow_id"] == record.workflow_id
    assert exported["status"] == WorkflowStatus.COMPLETED.value
    assert "artifacts" in exported
    assert "reasoning" in exported["artifacts"]
    assert "execution" in exported["artifacts"]


def test_start_unknown_workflow_raises(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    with pytest.raises(KeyError, match="not found"):
        workflow_engine.start_workflow("wf_missing")


def test_terminal_workflow_cannot_restart(
    workflow_engine: AutonomousWorkflowEngine,
) -> None:
    record = workflow_engine.create_workflow("Finished")
    record.status = WorkflowStatus.COMPLETED

    result = workflow_engine.start_workflow(record.workflow_id)
    assert result.success is False
    assert "terminal" in result.message


def test_brain_workflow_facades(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from agents.agent_manager import AgentManager
    from brain.brain import Brain
    from brain.llm import LLM
    from memory.learning_memory import LearningMemory
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from tools.tool_manager import ToolManager

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse."
    state = StateManager(file_path=tmp_path / "state.json")
    mission = MissionManager(file_path=tmp_path / "mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
        learning_memory=LearningMemory(file_path=tmp_path / "learning.json"),
    )

    assert hasattr(brain, "autonomous_workflow_engine")
    record = brain.create_workflow("Brain facade test")
    assert record.objective == "Brain facade test"
    assert brain.get_workflow(record.workflow_id) is record
    assert brain.list_workflows(limit=10)

    exported = brain.export_workflow(record.workflow_id)
    assert exported["objective"] == "Brain facade test"

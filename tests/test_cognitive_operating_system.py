# =====================================
# Titan Cognitive Operating System Tests
# =====================================

"""Comprehensive tests for Cognitive Operating System V1."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.cognitive_operating_system import (
    CognitiveOperatingSystem,
    CognitiveStage,
    ExecutionStatus,
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
from brain.developer_workflow import DeveloperWorkflowPlan, WorkflowIntent
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
from brain.world_model import WorldModelSnapshot
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from tools.tool_enums import RiskLevel
from tools.planner_models import ExecutionPlan as PlannerExecutionPlan
from tools.planner_models import PlannerResult, PlanStepKind


def _reasoning_result(
    message: str = "Test request",
    *,
    domain: ReasoningDomain = ReasoningDomain.GENERAL,
    open_questions: tuple[ReasoningQuestion, ...] = (),
) -> ReasoningResult:
    understanding = RequestUnderstanding(
        objective=message,
        constraints=(),
        urgency=ReasoningUrgency.NORMAL,
        domain=domain,
        requested_output="answer",
        raw_message=message,
    )
    summary = ReasoningSummary(
        objective=message,
        domain=domain,
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
            strategy="Proceed",
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


def _world_snapshot() -> WorldModelSnapshot:
    mock = MagicMock(spec=WorldModelSnapshot)
    mock.to_dict.return_value = {"summary": "World ok"}
    return mock


def _developer_plan() -> DeveloperWorkflowPlan:
    return DeveloperWorkflowPlan(
        goal="Implement feature",
        context_summary="Auth module refactor",
        intent=WorkflowIntent.GENERAL_DEVELOPMENT,
        risk_level=RiskLevel.LOW,
        relevant_files=(),
        recommended_tools=(),
        recommended_commands=(),
        test_plan=(),
        next_steps=("Review module",),
        requires_confirmation=False,
    )


def _planner_result() -> PlannerResult:
    execution_plan = PlannerExecutionPlan(
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
    node_count: int = 1,
    tool: str = "time",
) -> CognitivePlan:
    nodes = tuple(
        TaskGraphNode(
            node_id=f"node_{index}",
            objective=f"Step {index}",
            tool=tool,
            dependencies=(),
            cognitive_phase=CognitivePhase.PLANNING,
            step_kind=PlanStepKind.STANDARD,
        )
        for index in range(node_count)
    )
    order = tuple(node.node_id for node in nodes)
    return CognitivePlan(
        plan_id=plan_id,
        message="Test",
        task_graph=TaskGraph(nodes=nodes, execution_order=order),
        planner_result=_planner_result(),
        execution_plan=_planner_result().plan,
        analysis={},
        requires_confirmation=requires_confirmation,
        clarification_required=False,
    )


@pytest.fixture
def context_manager(tmp_path: Path) -> ContextManager:
    state = StateManager(file_path=tmp_path / "state.json")
    mission = MissionManager(file_path=tmp_path / "mission.json")
    return ContextManager(state_manager=state, mission_manager=mission)


@pytest.fixture
def cos(context_manager: ContextManager) -> CognitiveOperatingSystem:
    context_builder = MagicMock()
    reasoning_engine = MagicMock()
    executive_function = MagicMock()
    meta_cognition = MagicMock()
    knowledge_learning = MagicMock()
    world_model = MagicMock()
    memory_service = MagicMock()
    project_intelligence = MagicMock()
    developer_workflow = MagicMock()
    cognitive_orchestrator = MagicMock()
    workspace_awareness = MagicMock()

    context_builder.build_for_request.return_value = _cognitive_context()
    reasoning_engine.reason.return_value = _reasoning_result()
    executive_function.evaluate_missions.return_value = _executive_evaluation()
    meta_cognition.evaluate_reasoning.return_value = _meta_report()
    meta_cognition.requires_clarification.return_value = False
    meta_cognition.confidence.return_value = 0.9
    world_model.refresh.return_value = _world_snapshot()
    memory_service.retrieve.return_value = MagicMock(
        has_matches=False,
        items=(),
        user="Nolan",
        text="",
    )
    developer_workflow.plan.return_value = _developer_plan()

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

    return CognitiveOperatingSystem(
        cognitive_context_builder=context_builder,
        reasoning_engine=reasoning_engine,
        executive_function=executive_function,
        meta_cognition=meta_cognition,
        knowledge_learning_engine=knowledge_learning,
        world_model=world_model,
        memory_service=memory_service,
        project_intelligence=project_intelligence,
        developer_workflow=developer_workflow,
        cognitive_orchestrator=cognitive_orchestrator,
        context_manager=context_manager,
        workspace_awareness=workspace_awareness,
    )


def test_build_execution_plan_registers_execution(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("What time is it?")

    assert plan.plan_id.startswith("plan_")
    assert plan.execution_id.startswith("cos_")
    assert plan.request == "What time is it?"
    assert plan.reasoning is not None
    assert plan.cognitive_plan is not None
    assert plan.cognitive_context is not None
    assert plan.world_snapshot is not None


def test_build_execution_plan_rejects_empty_request(cos: CognitiveOperatingSystem) -> None:
    with pytest.raises(ValueError, match="request"):
        cos.build_execution_plan("   ")


def test_build_execution_plan_includes_code_subsystems_for_code_domain(
    cos: CognitiveOperatingSystem,
) -> None:
    cos._reasoning_engine.reason.return_value = _reasoning_result(
        "Refactor auth module",
        domain=ReasoningDomain.CODE,
    )
    architecture = MagicMock()
    architecture.to_dict.return_value = {"modules": 5}
    cos._project_intelligence.analyze_project.return_value = architecture

    plan = cos.build_execution_plan("Refactor auth module")

    cos._project_intelligence.analyze_project.assert_called_once()
    cos._developer_workflow.plan.assert_called_once()
    assert plan.architecture_summary is architecture
    assert plan.developer_plan is not None


def test_build_execution_plan_trace_records_stages(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("Analyze project")

    trace = cos.get_execution_trace(plan.execution_id)
    stage_names = [entry.stage for entry in trace.entries]

    assert CognitiveStage.RECEIVE in stage_names
    assert CognitiveStage.CONTEXT in stage_names
    assert CognitiveStage.REASON in stage_names
    assert CognitiveStage.EVALUATE in stage_names
    assert CognitiveStage.PLAN in stage_names


def test_build_execution_plan_metrics_track_subsystems(
    cos: CognitiveOperatingSystem,
) -> None:
    plan = cos.build_execution_plan("Track metrics")

    metrics = cos.get_execution_metrics(plan.execution_id)

    assert metrics.subsystem_calls.get("reasoning_engine", 0) >= 1
    assert metrics.subsystem_calls.get("cognitive_context_builder", 0) >= 1
    assert metrics.subsystem_calls.get("world_model", 0) >= 1
    assert metrics.stages_completed >= 5


def test_execute_plan_completes_successfully(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("What time is it?")
    result = cos.execute_plan(plan.plan_id)

    assert result.success is True
    assert result.execution.status == ExecutionStatus.COMPLETED
    assert result.execution_result is not None
    assert result.execution.learning_recorded is True
    cos._knowledge_learning_engine.learn_from_execution.assert_called_once()
    cos._knowledge_learning_engine.learn_from_reasoning.assert_called_once()


def test_process_request_full_lifecycle(cos: CognitiveOperatingSystem) -> None:
    result = cos.process_request("Run time tool")

    assert result.success is True
    assert result.plan is not None
    assert result.execution.status == ExecutionStatus.COMPLETED


def test_execute_plan_awaits_meta_cognition_clarification(
    cos: CognitiveOperatingSystem,
) -> None:
    cos._meta_cognition.requires_clarification.return_value = True
    cos._meta_cognition.evaluate_reasoning.return_value = _meta_report(
        clarification_required=True,
    )

    plan = cos.build_execution_plan("Ambiguous task")
    result = cos.execute_plan(plan.plan_id)

    assert result.success is False
    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION
    cos._cognitive_orchestrator.execute_plan.assert_not_called()


def test_execute_plan_awaits_low_confidence(cos: CognitiveOperatingSystem) -> None:
    cos._meta_cognition.confidence.return_value = 0.2
    cos._meta_cognition.evaluate_reasoning.return_value = _meta_report(confidence=0.2)

    plan = cos.build_execution_plan("Uncertain task")
    result = cos.execute_plan(plan.plan_id)

    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert "confidence" in result.message.lower()


def test_execute_plan_confirmed_skips_gate(cos: CognitiveOperatingSystem) -> None:
    cos._meta_cognition.requires_clarification.return_value = True
    plan = cos.build_execution_plan("Approved risky task")
    result = cos.execute_plan(plan.plan_id, confirmed=True)

    assert result.success is True
    cos._cognitive_orchestrator.execute_plan.assert_called_once()


def test_execute_plan_fails_verification(cos: CognitiveOperatingSystem) -> None:
    cos._cognitive_orchestrator.verify_plan.return_value = PlanVerificationResult(
        passed=False,
        summary="Step failed",
        failed_node_ids=("node_0",),
    )

    plan = cos.build_execution_plan("Failing task")
    result = cos.execute_plan(plan.plan_id)

    assert result.success is False
    assert result.execution.status == ExecutionStatus.FAILED


def test_execute_plan_suspended_execution(cos: CognitiveOperatingSystem) -> None:
    plan_obj = _cognitive_plan()
    runtime = PlanRuntimeState(plan_id=plan_obj.plan_id, status=PlanStatus.SUSPENDED)
    cos._cognitive_orchestrator.create_plan.return_value = plan_obj
    cos._cognitive_orchestrator.execute_plan.return_value = runtime

    plan = cos.build_execution_plan("Needs confirmation")
    result = cos.execute_plan(plan.plan_id)

    assert result.execution.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert "confirmation" in result.message.lower()


def test_cancel_execution(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("Cancel me")
    cancelled = cos.cancel_execution(plan.execution_id)

    assert cancelled is not None
    assert cancelled.status == ExecutionStatus.CANCELLED


def test_cancel_terminal_execution_returns_none(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("Done")
    cos.execute_plan(plan.plan_id)

    assert cos.cancel_execution(plan.execution_id) is None


def test_export_execution_includes_trace_and_metrics(cos: CognitiveOperatingSystem) -> None:
    plan = cos.build_execution_plan("Export test")
    cos.execute_plan(plan.plan_id)

    exported = cos.export_execution(plan.execution_id)

    assert exported["execution_id"] == plan.execution_id
    assert exported["status"] == ExecutionStatus.COMPLETED.value
    assert "trace" in exported
    assert "metrics" in exported
    assert "plan" in exported
    assert "artifacts" in exported


def test_get_execution_and_list(cos: CognitiveOperatingSystem) -> None:
    first = cos.build_execution_plan("First")
    second = cos.build_execution_plan("Second")

    assert cos.get_execution(first.execution_id) is not None
    assert len(cos.list_executions()) == 2


def test_execute_unknown_plan_raises(cos: CognitiveOperatingSystem) -> None:
    with pytest.raises(KeyError, match="not found"):
        cos.execute_plan("plan_missing")


def test_brain_cognitive_os_facades(tmp_path: Path) -> None:
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

    assert hasattr(brain, "cognitive_operating_system")
    plan = brain.build_cognitive_execution_plan("Brain COS facade test")
    assert plan.request == "Brain COS facade test"
    assert brain.get_cognitive_execution(plan.execution_id) is not None

    exported = brain.export_cognitive_execution(plan.execution_id)
    assert exported["request"] == "Brain COS facade test"
    assert brain.list_cognitive_executions(limit=10)

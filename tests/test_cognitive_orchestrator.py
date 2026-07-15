# =====================================
# Titan Cognitive Orchestrator Tests
# =====================================

"""Tests for Phase 24.0 — Cognitive Orchestrator (P24-010)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.cognitive_models import (
    CognitivePhase,
    PlanStatus,
    TaskNodeStatus,
)
from brain.cognitive_orchestrator import CognitiveOrchestrator
from brain.cognitive_progress import (
    progress_label_for_phase,
    progress_label_for_tool,
    register_tool_presentation,
    resolve_neural_state,
    resolve_tool_phase,
)
from brain.executor import Executor
from brain.reasoning import Reasoning
from core.execution_policy import ExecutionPolicy
from tools.decision.intent import Intent
from tools.decision.models import CandidateTool, ToolDecisionReport
from tools.natural_language_planner import NaturalLanguagePlanner
from tools.orchestration_models import OrchestrationStatus, ToolOrchestrationResult
from tools.permission_manager import PermissionManager
from tools.reasoning_loop import ReasoningLoop
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest, ToolResult


@pytest.fixture
def tmp_tool_manager(tmp_path: Path) -> ToolManager:
    return ToolManager(project_root=tmp_path, use_runtime_v2=True)


@pytest.fixture
def orchestrator(tmp_tool_manager: ToolManager) -> CognitiveOrchestrator:
    tool_orchestrator = ToolOrchestrator(tmp_tool_manager)
    planner = NaturalLanguagePlanner(
        permission_manager=tool_orchestrator.permission_manager,
    )
    reasoning_loop = ReasoningLoop(
        permission_manager=tool_orchestrator.permission_manager,
    )
    return CognitiveOrchestrator(
        reasoning=Reasoning(project_root=tmp_tool_manager.project_root),
        planner=planner,
        reasoning_loop=reasoning_loop,
        tool_orchestrator=tool_orchestrator,
        executor=Executor(),
        policy=ExecutionPolicy(max_tools=5),
        tool_manager=tmp_tool_manager,
    )


def _time_analysis() -> dict:
    report = ToolDecisionReport(
        intent=Intent.SYSTEM,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(CandidateTool(tool_name="time", score=0.9, reason="time"),),
        selected_tool="time",
        decision_reason="time request",
        risk_level=RiskLevel.SAFE,
        confirmation_required=False,
    )
    return {
        "needs_tool": True,
        "needs_clarification": False,
        "tool_requests": [ToolRequest("time", {})],
        "decision_report": report,
    }


def test_create_plan_builds_task_graph(orchestrator: CognitiveOrchestrator) -> None:
    plan = orchestrator.create_plan(
        "Quelle heure est-il ?",
        analysis=_time_analysis(),
    )

    assert plan.plan_id.startswith("plan_")
    assert plan.total_steps >= 1
    assert "time" in plan.estimated_tools
    assert plan.task_graph.node_count >= 1
    assert orchestrator.get_runtime(plan.plan_id) is not None


def test_create_plan_records_understanding_progress(
    orchestrator: CognitiveOrchestrator,
) -> None:
    events: list = []
    orchestrator.on_progress = lambda event: events.append(event)

    plan = orchestrator.create_plan("Quelle heure est-il ?", analysis=_time_analysis())
    runtime = orchestrator.get_runtime(plan.plan_id)

    assert runtime is not None
    assert any(event.phase == CognitivePhase.UNDERSTANDING for event in runtime.progress_events)
    assert any(event.phase == CognitivePhase.PLANNING for event in runtime.progress_events)


def test_execute_and_verify_plan(orchestrator: CognitiveOrchestrator) -> None:
    plan = orchestrator.create_plan("Quelle heure est-il ?", analysis=_time_analysis())
    runtime = orchestrator.execute_plan(plan, message="Quelle heure est-il ?")
    verification = orchestrator.verify_plan(plan, runtime)

    assert verification.passed
    assert runtime.status == PlanStatus.COMPLETED
    assert runtime.tool_results


def test_run_turn_full_pipeline(orchestrator: CognitiveOrchestrator) -> None:
    result = orchestrator.run_turn(
        "Quelle heure est-il ?",
        analysis=_time_analysis(),
    )

    assert result.verification.passed
    assert result.tool_results
    assert result.plan.total_steps >= 1


def test_cancel_plan(orchestrator: CognitiveOrchestrator) -> None:
    plan = orchestrator.create_plan("Quelle heure est-il ?", analysis=_time_analysis())
    runtime = orchestrator.cancel_plan(plan.plan_id)

    assert runtime is not None
    assert runtime.status == PlanStatus.CANCELLED
    assert orchestrator.get_runtime(plan.plan_id) is None


def test_retry_step(orchestrator: CognitiveOrchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = orchestrator.create_plan("Quelle heure est-il ?", analysis=_time_analysis())
    step_id = plan.task_graph.execution_order[0]

    fake_result = ToolOrchestrationResult(
        orchestration_status=OrchestrationStatus.COMPLETED,
        selected_tool="time",
        selected_action=None,
        permission_level=PermissionManager().evaluate("time", "now", {}).level,
        executed=True,
        confirmation_required=False,
        reason="ok",
        result=ToolResult(tool_name="time", success=True, data="12:00", source="time"),
    )
    monkeypatch.setattr(
        orchestrator.tool_orchestrator,
        "orchestrate",
        MagicMock(return_value=fake_result),
    )

    runtime = orchestrator.retry_step(plan, step_id, message="Quelle heure est-il ?")

    assert runtime.node_status[step_id] == TaskNodeStatus.COMPLETED


def test_progress_labels_never_expose_reasoning() -> None:
    label = progress_label_for_phase(CognitivePhase.UNDERSTANDING)
    assert "reasoning" not in label.lower()
    assert "chain" not in label.lower()
    assert "…" in label or label.endswith(".")


def test_tool_phase_mapping() -> None:
    assert resolve_tool_phase("obsidian") == CognitivePhase.MEMORY
    assert resolve_tool_phase("browser") == CognitivePhase.RESEARCH
    assert resolve_tool_phase("email") == CognitivePhase.WRITING
    assert resolve_tool_phase("calendar") == CognitivePhase.PLANNING


def test_neural_state_mapping() -> None:
    assert resolve_neural_state(CognitivePhase.MEMORY) == "memory_retrieval"
    assert resolve_neural_state(CognitivePhase.PLANNING) == "planning"
    assert resolve_neural_state(CognitivePhase.RESEARCH, "browser") == "browser_research"


def test_register_future_tool() -> None:
    register_tool_presentation(
        "custom_agent",
        phase=CognitivePhase.RESEARCH,
        label="Exploration spécialisée…",
        neural_state="browser_research",
    )
    assert resolve_tool_phase("custom_agent") == CognitivePhase.RESEARCH
    assert progress_label_for_tool("custom_agent") == "Exploration spécialisée…"


def test_execution_coordinator_uses_cognitive_orchestrator(tmp_path: Path) -> None:
    from agents.agent_manager import AgentManager
    from brain.tool_dispatcher import ToolDispatcher
    from core.execution_coordinator import ExecutionCoordinator
    from core.task_orchestrator import TaskOrchestrator
    from core.task_manager import TaskManager

    tool_manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    agent_manager = AgentManager()
    task_orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    coordinator = ExecutionCoordinator(
        task_orchestrator,
        ToolDispatcher(tool_manager),
        reasoning=Reasoning(project_root=tmp_path),
    )

    result = coordinator.execute("Quelle heure est-il ?")

    assert result.cognitive_execution is not None
    assert result.cognitive_execution.verification.passed


def test_orchestrator_progress_formatter() -> None:
    from api.orchestrator_progress import format_orchestrator_progress
    from brain.cognitive_models import (
        CognitiveExecutionResult,
        CognitivePlan,
        PlanRuntimeState,
        PlanVerificationResult,
        ProgressEvent,
        TaskGraph,
    )
    from brain.pipeline.context_bundle import ThinkContext
    from tools.planner_models import ExecutionPlan, PlannerResult

    execution_plan = ExecutionPlan(
        overall_goal="test",
        plan_summary="test",
        steps=(),
        execution_order=(),
    )
    planner_result = PlannerResult.from_execution_plan(execution_plan)
    plan = CognitivePlan(
        plan_id="plan_test",
        message="test",
        task_graph=TaskGraph(nodes=(), execution_order=()),
        planner_result=planner_result,
        execution_plan=execution_plan,
        analysis={},
    )
    runtime = PlanRuntimeState(plan_id="plan_test")
    runtime.progress_events = [
        ProgressEvent(
            phase=CognitivePhase.UNDERSTANDING,
            label=progress_label_for_phase(CognitivePhase.UNDERSTANDING),
        ),
        ProgressEvent(
            phase=CognitivePhase.MEMORY,
            label=progress_label_for_tool("obsidian"),
            tool="obsidian",
        ),
    ]
    cognitive = CognitiveExecutionResult(
        plan=plan,
        runtime=runtime,
        verification=PlanVerificationResult(passed=True, summary="ok"),
        tool_results=(),
        orchestration_results=(),
    )
    ctx = ThinkContext(user_message="test", cognitive_execution=cognitive)
    progress = format_orchestrator_progress(ctx)

    assert len(progress) >= 2
    assert all("reasoning" not in item["label"].lower() for item in progress)
    assert progress[0]["neural_state"] == "thinking"
    assert progress[1]["neural_state"] == "memory_retrieval"

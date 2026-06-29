# =====================================
# Titan Decision Runtime Integration Tests
# =====================================

"""Integration tests for Phase 10B Batch 2 — Decision Runtime Integration (P10B-101–P10B-106)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.decision_execution_bridge import availability_resolver_from_manager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from brain.tool_execution_bridge import ExecutionDispatchContext, build_tool_execution_context
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.execution_context import extract_decision_report
from tools.decision.models import FallbackAction
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.tool_enums import RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager
from tools.tool_result import ToolRequest
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus


@pytest.fixture
def runtime_tool_manager(tmp_path) -> ToolManager:
    return ToolManager(project_root=tmp_path, use_runtime_v2=True)


@pytest.fixture
def legacy_tool_manager(tmp_path) -> ToolManager:
    return ToolManager(project_root=tmp_path, use_runtime_v2=False)


@pytest.fixture
def runtime_coordinator(
    runtime_tool_manager: ToolManager,
    mock_agent_llm: MagicMock,
) -> ExecutionCoordinator:
    dispatcher = ToolDispatcher(runtime_tool_manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    return ExecutionCoordinator(
        orchestrator,
        dispatcher,
        reasoning=Reasoning(),
    )


def test_decision_to_runtime_successful_execution(
    runtime_coordinator: ExecutionCoordinator,
) -> None:
    """P10B-101/106: Decision → Coordinator → Runtime executes time tool."""
    result = runtime_coordinator.execute("Quelle heure est-il ?")
    assert result.decision_report is not None
    assert result.decision_report.selected_tool == "time"
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success
    assert result.tool_results[0].tool_name == "time"


def test_decision_report_in_execution_context(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-105: DecisionReport is attached to ToolExecutionContext metadata."""
    reasoning = Reasoning()
    resolver = availability_resolver_from_manager(runtime_tool_manager)
    analysis = reasoning.analyze(
        "Quelle heure est-il ?",
        availability_resolver=resolver,
    )
    report = analysis["decision_report"]
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        decision_report=report,
    )
    ctx = build_tool_execution_context(dispatch)
    restored = extract_decision_report(ctx)
    assert restored is not None
    assert restored.selected_tool == report.selected_tool
    assert restored.to_dict() == report.to_dict()


def test_decision_to_confirmation_required(
    runtime_coordinator: ExecutionCoordinator,
) -> None:
    """P10B-102/104: High-risk tool surfaces pending confirmation, not silent skip."""
    result = runtime_coordinator.execute("Exécute python: print('risky')")
    assert result.decision_report is not None
    assert result.decision_report.confirmation_required is True
    assert len(result.tool_results) == 1
    tool_result = result.tool_results[0]
    assert tool_result.success is False
    assert tool_result.metadata.get("pending_confirmation") is True
    assert "Confirmation requise" in tool_result.error or "Confirmer" in tool_result.error


def test_decision_to_no_capability_surfaces_error(
    runtime_coordinator: ExecutionCoordinator,
) -> None:
    """P10B-104: NO_CAPABILITY produces explicit decision_engine tool result."""
    result = runtime_coordinator.execute("Send an email to Ibrahim")
    assert result.decision_report is not None
    assert result.decision_report.fallback_action == FallbackAction.NO_CAPABILITY
    assert len(result.tool_results) == 1
    tool_result = result.tool_results[0]
    assert tool_result.success is False
    assert tool_result.source == "decision_engine"
    assert "Capacité indisponible" in tool_result.error
    assert result.tool_results_text


def test_provider_health_excludes_offline_tool(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-103: Offline provider health removes tool from available set."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    runtime.health_monitor.set_tool_health("time", ToolHealthState.OFFLINE)

    resolver = CapabilityAvailabilityResolver(
        catalog=runtime.catalog,
        health_monitor=runtime.health_monitor,
        provider_registry=runtime_tool_manager.provider_registry,
    )
    report = ToolDecisionEngine().decide(
        "Quelle heure est-il ?",
        availability_resolver=resolver,
    )
    assert report.fallback_action == FallbackAction.NO_CAPABILITY


def test_disabled_provider_excludes_dependent_tool(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-103: Disabled provider excludes tools bound to that provider."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    capability = runtime.catalog.get("web_search")
    assert capability is not None
    assert capability.provider_name
    runtime.health_monitor.set_provider_health(
        capability.provider_name,
        ToolHealthState.DISABLED,
    )

    resolver = CapabilityAvailabilityResolver(
        catalog=runtime.catalog,
        health_monitor=runtime.health_monitor,
        provider_registry=runtime_tool_manager.provider_registry,
    )
    report = ToolDecisionEngine().decide(
        "Search the latest NQ news",
        availability_resolver=resolver,
    )
    assert report.fallback_action == FallbackAction.NO_CAPABILITY


def test_degraded_provider_lowers_ranking(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-103: Degraded health penalizes candidate score."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    runtime.health_monitor.set_tool_health("time", ToolHealthState.DEGRADED)

    resolver = CapabilityAvailabilityResolver(
        catalog=runtime.catalog,
        health_monitor=runtime.health_monitor,
        provider_registry=runtime_tool_manager.provider_registry,
    )
    engine = ToolDecisionEngine()
    baseline = engine.decide("Quelle heure est-il ?")
    degraded = engine.decide("Quelle heure est-il ?", availability_resolver=resolver)
    assert baseline.selected_tool == "time"
    assert degraded.candidate_tools
    degraded_time = next(
        (item for item in degraded.candidate_tools if item.tool_name == "time"),
        None,
    )
    baseline_time = next(
        (item for item in baseline.candidate_tools if item.tool_name == "time"),
        None,
    )
    assert degraded_time is not None
    assert baseline_time is not None
    assert degraded_time.score < baseline_time.score


def test_runtime_failure_surfaces_error(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-104: Runtime execution failure returns explicit ToolResult error."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    outcome = runtime.invoke("file_read", {"path": ""}, ctx)
    result = runtime.outcome_to_result(outcome)
    assert result.success is False
    assert result.error


def test_decision_mismatch_blocked_by_runtime(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10B-102: Runtime rejects tool when DecisionReport selected_tool mismatches."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    reasoning = Reasoning()
    resolver = availability_resolver_from_manager(runtime_tool_manager)
    analysis = reasoning.analyze(
        "Quelle heure est-il ?",
        availability_resolver=resolver,
    )
    report = analysis["decision_report"]
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        decision_report=report,
    )
    ctx = build_tool_execution_context(dispatch)
    outcome = runtime.invoke("web_search", {"query": "mismatch"}, ctx)
    assert outcome.status == ToolRunStatus.FAILED
    assert "incohérence" in (outcome.error or "").lower()


def test_legacy_runtime_still_executes(
    legacy_tool_manager: ToolManager,
    mock_agent_llm: MagicMock,
) -> None:
    """Backward compatibility: legacy path executes without DecisionReport in runtime."""
    dispatcher = ToolDispatcher(legacy_tool_manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].success
    assert legacy_tool_manager.runtime is None


def test_legacy_runtime_no_capability_still_surfaces(
    legacy_tool_manager: ToolManager,
    mock_agent_llm: MagicMock,
) -> None:
    """Legacy path still surfaces NO_CAPABILITY via decision engine analysis."""
    dispatcher = ToolDispatcher(legacy_tool_manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Send an email to Nolan")
    assert result.decision_report is not None
    assert result.decision_report.fallback_action == FallbackAction.NO_CAPABILITY
    assert result.tool_results[0].source == "decision_engine"


def test_think_context_receives_decision_report(
    runtime_coordinator: ExecutionCoordinator,
) -> None:
    """P10B-101: ThinkContext stores decision_report after execution coordinate."""
    from brain.pipeline.context_bundle import ThinkContext
    from brain.tool_execution_bridge import dispatch_context_from_think

    ctx = ThinkContext(user_message="Quelle heure est-il ?")
    dispatch = dispatch_context_from_think(ctx)
    result = runtime_coordinator.execute(
        ctx.user_message,
        dispatch_context=dispatch,
    )
    ctx.decision_report = result.decision_report
    ctx.tool_results = result.tool_results
    assert ctx.decision_report is not None
    assert ctx.decision_report.selected_tool == "time"


def test_decision_engine_opt_out_regression(
    legacy_tool_manager: ToolManager,
    mock_agent_llm: MagicMock,
) -> None:
    """Regression: TITAN_TOOL_DECISION_ENGINE opt-out preserves keyword path."""
    dispatcher = ToolDispatcher(legacy_tool_manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(
        orchestrator,
        dispatcher,
        reasoning=Reasoning(use_decision_engine=False),
    )
    result = coordinator.execute("Quelle heure est-il ?")
    assert result.decision_report is None
    assert result.tool_results[0].tool_name == "time"

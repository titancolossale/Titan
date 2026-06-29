# =====================================
# Titan Execution Coordinator Tests
# =====================================

"""Tests for Phase 8 ExecutionCoordinator (P8-060–P8-070)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.agent_context import AgentContext
from agents.agent_manager import AgentManager
from agents.agent_result import AgentResult
from brain.executor import Executor
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.execution_policy import ExecutionPolicy
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.tool_manager import ToolManager
from tools.tool_result import ToolRequest, ToolResult


@pytest.fixture
def coordinator(tmp_path) -> ExecutionCoordinator:
    tool_manager = ToolManager(project_root=tmp_path)
    dispatcher = ToolDispatcher(tool_manager)
    agent_manager = MagicMock(spec=AgentManager)
    agent_manager.execute.return_value = AgentResult(
        agent_name="coding",
        task="test",
        summary="mock result",
        confidence=0.9,
    )
    task_orchestrator = TaskOrchestrator(
        TaskManager(agent_manager),
        agent_manager,
    )
    return ExecutionCoordinator(
        task_orchestrator,
        dispatcher,
        reasoning=Reasoning(),
        executor=Executor(),
    )


def test_execution_policy_clamps_agents() -> None:
    """P8-060: max_agents policy enforced."""
    policy = ExecutionPolicy(max_agents=2)
    assert policy.clamp_agent_count(5) == 2
    assert policy.clamp_agent_count(1) == 1


def test_execution_policy_clamps_tools() -> None:
    """P8-060: max_tools policy enforced."""
    policy = ExecutionPolicy(max_tools=1)
    assert policy.clamp_tool_count(3) == 1


def test_coordinator_runs_agents(coordinator: ExecutionCoordinator) -> None:
    """P8-062: execute returns agent results."""
    coordinator.task_orchestrator.task_manager.create_tasks = MagicMock(
        return_value=[("coding", "Écrire du code")],
    )
    result = coordinator.execute("Écris une fonction Python")
    assert len(result.agent_results) == 1
    assert "coding" in result.agent_results_text


def test_coordinator_runs_tools_on_time_request(
    coordinator: ExecutionCoordinator,
) -> None:
    """P8-062: time tool requests produce tool_results."""
    coordinator.task_orchestrator.task_manager.create_tasks = MagicMock(
        return_value=[],
    )
    result = coordinator.execute("Quelle heure est-il ?")
    assert len(result.tool_results) == 1
    assert result.tool_results[0].tool_name == "time"


def test_coordinator_truncates_agents(tmp_path) -> None:
    """P8-063: agent pipeline truncated to max_agents."""
    tool_manager = ToolManager(project_root=tmp_path)
    dispatcher = ToolDispatcher(tool_manager)
    agent_manager = MagicMock(spec=AgentManager)
    agent_manager.execute.return_value = AgentResult(
        agent_name="x",
        task="t",
        summary="ok",
        confidence=1.0,
    )
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(
        return_value=[
            ("a", "t1"),
            ("b", "t2"),
            ("c", "t3"),
            ("d", "t4"),
        ],
    )
    coord = ExecutionCoordinator(
        orchestrator,
        dispatcher,
        policy=ExecutionPolicy(max_agents=2),
    )
    result = coord.execute("code python complexe")
    assert len(result.agent_results) == 2


def test_pipeline_uses_execution_coordinate_stage() -> None:
    """P8-063: pipeline replaced agent_orchestration + tool_dispatch."""
    from brain.pipeline.stages import STAGE_ORDER

    assert "execution_coordinate" in STAGE_ORDER
    assert "agent_orchestration" not in STAGE_ORDER
    assert "tool_dispatch" not in STAGE_ORDER
    assert STAGE_ORDER.index("execution_coordinate") < STAGE_ORDER.index("llm_call")

# =====================================
# Titan Phase 12.8 Consolidation Tests
# =====================================

"""Regression tests for Phase 12.8 core architecture consolidation (P128-005)."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.tool_dispatcher import ToolDispatcher
from core.execution_context import ExecutionDispatchContext, build_tool_execution_context
from core.execution_coordinator import ExecutionCoordinator
from core.execution_policy import ExecutionPolicy
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.default_tools import build_default_tools, register_default_tools
from tools.permission_facade import PermissionFacade
from tools.permission_manager import PermissionLevel
from tools.tool_executor import execute_tool
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest
from tools.tool_policy import BRAIN_CALLER


def test_execution_context_lives_in_core_not_brain() -> None:
    """P128-001: tools layer imports dispatch context from core, not brain."""
    import core.execution_context as module

    assert hasattr(module, "ExecutionDispatchContext")
    assert hasattr(module, "build_tool_execution_context")


def test_tool_orchestrator_does_not_import_brain() -> None:
    """P128-001: ToolOrchestrator must not depend on brain package."""
    import tools.tool_orchestrator as module

    source_path = Path(module.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    assert "from brain." not in source
    assert "import brain." not in source


def test_unified_executor_matches_dispatcher(tmp_path: Path) -> None:
    """P128-002: tool_executor and ToolDispatcher produce equivalent time results."""
    manager = ToolManager(project_root=tmp_path)
    dispatcher = ToolDispatcher(manager)
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="test",
        turn_id="turn-1",
    )

    via_dispatcher = dispatcher.dispatch(
        [ToolRequest("time", {})],
        dispatch_context=dispatch,
    )
    via_executor = execute_tool(
        manager,
        "time",
        {},
        caller=BRAIN_CALLER,
        dispatch_context=dispatch,
    )

    assert via_dispatcher[0].success == via_executor.success
    assert via_dispatcher[0].tool_name == via_executor.tool_name


def test_task_execution_engine_uses_orchestrator_invoke(tmp_path: Path) -> None:
    """P128-002: multi-step tasks route through ToolOrchestrator, not raw dispatcher."""
    from unittest.mock import MagicMock

    from agents.agent_manager import AgentManager

    manager = ToolManager(project_root=tmp_path)
    dispatcher = ToolDispatcher(manager)
    agent_manager = MagicMock(spec=AgentManager)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    coord = ExecutionCoordinator(
        orchestrator,
        dispatcher,
        policy=ExecutionPolicy(max_agents=4, max_tools=4),
    )

    invoke = coord._orchestrator_invoke(
        ExecutionDispatchContext(user="Nolan", session_id="s", turn_id="t"),
        None,
    )
    result = invoke(ToolRequest("time", {}))
    assert result.tool_name == "time"
    assert result.success


def test_task_orchestrator_delegates_agent_truncation() -> None:
    """P128-001: TaskOrchestrator.orchestrate honors max_agents."""
    from unittest.mock import MagicMock

    from agents.agent_manager import AgentManager
    from agents.agent_result import AgentResult

    agent_manager = MagicMock(spec=AgentManager)
    agent_manager.execute.return_value = AgentResult(
        agent_name="coding",
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
        ],
    )
    results = orchestrator.orchestrate("code", max_agents=2)
    assert len(results) == 2


def test_default_tools_registration(tmp_path: Path) -> None:
    """P128-004: central registry registers all built-in tools."""
    manager = ToolManager(project_root=tmp_path, register_defaults=False)
    register_default_tools(
        manager.registry,
        tmp_path,
        provider_executor=manager.provider_executor,
    )
    names = set(manager.list_tools())
    expected = {tool.name for tool in build_default_tools(tmp_path)}
    assert expected.issubset(names)


def test_permission_facade_combines_engine_and_manager() -> None:
    """P128-003: PermissionFacade evaluates caller and action in one call."""
    from tools.tool_run_models import ToolExecutionContext

    facade = PermissionFacade()
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="default",
        turn_id="default",
    )
    result = facade.evaluate("time", None, ctx, {})
    assert result.allowed
    assert result.level == PermissionLevel.AUTO_ALLOWED

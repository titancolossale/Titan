# =====================================
# Titan Brain Tool Integration Tests
# =====================================

"""Tests for Phase 10A Batch 6 — Brain → ExecutionCoordinator → ToolRuntime (P10A-028)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain.brain import Brain
from brain.pipeline.context_bundle import ThinkContext
from brain.prompt_builder import PromptBuilder
from brain.tool_confirmation_handler import (
    is_pure_confirmation_command,
    parse_confirmation_token,
    resolve_confirmed_tool_requests,
)
from brain.tool_dispatcher import ToolDispatcher
from brain.tool_execution_bridge import (
    ExecutionDispatchContext,
    build_tool_execution_context,
    dispatch_context_from_think,
)
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.confirmation_gate import ConfirmationGate
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_manager import ToolManager
from tools.tool_result import ToolRequest
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus
from tools.tool_status_formatter import ToolStatusFormatter


@pytest.fixture
def runtime_tool_manager(tmp_path) -> ToolManager:
    """ToolManager with runtime v2 enabled for integration tests."""
    return ToolManager(project_root=tmp_path, use_runtime_v2=True)


@pytest.fixture
def runtime_dispatcher(runtime_tool_manager: ToolManager) -> ToolDispatcher:
    return ToolDispatcher(runtime_tool_manager)


def test_dispatch_context_from_think_context() -> None:
    """P10A-025: ThinkContext maps to ExecutionDispatchContext."""
    ctx = ThinkContext(
        user_message="test",
        current_user="Ibrahim",
        session_id="sess-1",
        turn_id="turn-3",
        tool_confirmed=True,
        confirmation_token="abc-123",
    )
    dispatch = dispatch_context_from_think(ctx)
    assert dispatch.user == "Ibrahim"
    assert dispatch.session_id == "sess-1"
    assert dispatch.turn_id == "turn-3"
    assert dispatch.confirmed is True
    assert dispatch.confirmation_token == "abc-123"


def test_build_tool_execution_context_preserves_confirmation() -> None:
    """P10A-025: confirmation fields flow into ToolExecutionContext."""
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        confirmed=True,
        confirmation_token="tok",
    )
    ctx = build_tool_execution_context(dispatch)
    assert ctx.confirmed is True
    assert ctx.confirmation_token == "tok"


def test_dispatcher_routes_through_runtime_v2(
    runtime_dispatcher: ToolDispatcher,
) -> None:
    """P10A-028: v2 dispatcher invokes ToolRuntime, not legacy registry only."""
    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="s1",
        turn_id="t1",
    )
    results = runtime_dispatcher.dispatch(
        [ToolRequest("time", {})],
        dispatch_context=dispatch,
    )
    assert len(results) == 1
    assert results[0].success
    assert results[0].tool_name == "time"


def test_dispatcher_legacy_fallback_when_runtime_disabled(tmp_path) -> None:
    """P10A-028: backward compatibility when TITAN_TOOL_RUNTIME_V2 is off."""
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=False)
    dispatcher = ToolDispatcher(manager)
    assert manager.runtime is None
    results = dispatcher.dispatch([ToolRequest("time", {})])
    assert len(results) == 1
    assert results[0].success


def test_probe_provider_health_in_prompt(runtime_dispatcher: ToolDispatcher) -> None:
    """P10A-026: provider health appears in formatted status block."""
    text = runtime_dispatcher.probe_provider_health()
    assert "Providers :" in text
    assert "web_search" in text
    assert "Outils (capability-first)" in text


def test_prompt_builder_includes_tool_health_section() -> None:
    """P10A-026: PromptBuilder renders SANTÉ OUTILS ET PROVIDERS."""
    ctx = ThinkContext(
        user_message="test",
        tool_status_text="Providers :\n  - web_search v1.0.0 : online",
    )
    prompt = PromptBuilder().build(ctx)
    assert "SANTÉ OUTILS ET PROVIDERS" in prompt
    assert "web_search" in prompt


def test_execution_coordinator_passes_dispatch_context(
    runtime_dispatcher: ToolDispatcher,
    mock_agent_llm: MagicMock,
) -> None:
    """P10A-028: coordinator forwards dispatch context to ToolDispatcher."""
    from agents.agent_manager import AgentManager
    from memory.memory_service import MemoryService
    from memory.memory_manager import MemoryManager
    from memory.long_term_memory import LongTermMemory

    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, runtime_dispatcher)

    dispatch = ExecutionDispatchContext(
        user="Nolan",
        session_id="brain-s1",
        turn_id="brain-t1",
    )
    result = coordinator.execute(
        "Quelle heure est-il ?",
        dispatch_context=dispatch,
    )
    assert len(result.tool_results) == 1
    assert result.tool_results[0].tool_name == "time"


def test_confirmation_command_parsing() -> None:
    """P10A-027: /confirm and confirme parse UUID tokens."""
    token = "a46c42b3-5b94-416f-b294-c76704c140e6"
    assert parse_confirmation_token(f"/confirm {token}") == token
    assert parse_confirmation_token(f"confirme {token}") == token
    assert is_pure_confirmation_command(f"/confirm {token}") is True
    assert parse_confirmation_token("Bonjour") is None


def test_confirmation_resolves_pending_tool_request(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10A-027: confirmed command re-dispatches stored pending params."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    gate = runtime.confirmation_gate

    cap = ToolCapability(
        name="python_exec",
        description="exec",
        parameters=(),
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
    )
    params = {"code": "print('ok')"}
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="sess-a",
        turn_id="turn-1",
    )
    pending = gate.evaluate("python_exec", cap, ctx, params)
    assert pending.request is not None

    requests, dispatch = resolve_confirmed_tool_requests(
        f"/confirm {pending.request.token}",
        gate,
        session_id="sess-a",
        user="Nolan",
        turn_id="turn-2",
    )
    assert dispatch is not None
    assert dispatch.confirmed is True
    assert len(requests) == 1
    assert requests[0].tool_name == "python_exec"
    assert requests[0].params == params


def test_end_to_end_confirmation_via_runtime(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10A-027: confirmed re-invocation executes through ToolRuntime."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    gate = runtime.confirmation_gate

    params = {"code": "print('confirmed')"}
    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="sess-b",
        turn_id="t1",
    )
    cap = runtime.catalog.get("python_exec")
    assert cap is not None
    pending = gate.evaluate("python_exec", cap, ctx, params)
    assert pending.request is not None

    confirmed_ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="sess-b",
        turn_id="t2",
        confirmed=True,
        confirmation_token=pending.request.token,
    )
    outcome = runtime.invoke("python_exec", params, confirmed_ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.success


def test_brain_think_includes_provider_health_with_runtime_v2(
    tmp_path,
    mock_agent_llm: MagicMock,
) -> None:
    """P10A-028: full think() pipeline injects provider health when v2 enabled."""
    from brain.llm import LLM
    from context.context_manager import ContextManager
    from core.conversation_engine import ConversationEngine
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from agents.agent_manager import AgentManager

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse."

    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    brain = Brain(
        agent_manager=AgentManager(agent_llm=mock_agent_llm),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=MemoryService(
            short_term=MemoryManager(),
            long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
        ),
        tool_manager=ToolManager(project_root=tmp_path, use_runtime_v2=True),
        conversation_engine=ConversationEngine(persist_sessions=False),
        llm=mock_llm,
    )

    brain.think("Quelle heure est-il ?")
    prompt_sent = mock_llm.ask.call_args[0][0]
    assert "SANTÉ OUTILS ET PROVIDERS" in prompt_sent
    assert "RÉSULTATS OUTILS" in prompt_sent


def test_tool_status_formatter_probe_snapshot(
    runtime_tool_manager: ToolManager,
) -> None:
    """P10A-026: snapshot aggregates provider and tool health."""
    runtime = runtime_tool_manager.runtime
    assert runtime is not None
    snapshot = ToolStatusFormatter.probe_snapshot(
        runtime_tool_manager.provider_registry,
        runtime.health_monitor,
        runtime.catalog,
    )
    assert "web_search" in snapshot.provider_health
    assert "time" in snapshot.tool_health

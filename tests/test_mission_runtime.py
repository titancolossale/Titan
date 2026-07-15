# =====================================
# Titan Mission Runtime Tests
# =====================================

"""Tests for Mission Runtime V1 — lifecycle, progress, Brain integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.brain import Brain
from brain.llm import LLM
from agents.agent_manager import AgentManager
from context.context_manager import ContextManager
from core.conversation_engine import ConversationEngine
from core.mission_manager import MissionManager
from core.mission_models import MissionState
from core.mission_runtime import MissionRuntime
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


@pytest.fixture
def runtime(tmp_path: Path) -> MissionRuntime:
    return MissionRuntime(file_path=tmp_path / "titan_mission.json")


def test_mission_creation(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission(
        title="Build Trading Bot",
        objective="Create NQ trading automation",
        steps=["Backtest", "Execution", "Risk"],
    )

    assert mission.title == "Build Trading Bot"
    assert mission.objective == "Create NQ trading automation"
    assert mission.state in {MissionState.CREATED, MissionState.READY}
    assert mission.current_step == "Backtest"
    assert mission.completed_steps == []
    assert mission.remaining_steps == ["Backtest", "Execution", "Risk"]
    assert mission.progress_percent == 0.0
    assert mission.history[0].event == "mission_created"
    assert runtime.get_active_mission() is not None
    assert runtime.get_active_mission().id == mission.id


def test_mission_progress(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Progress Test", "Obj", ["A", "B", "C"])
    runtime.complete_current_step(mission.id)

    updated = runtime.get_mission(mission.id)
    assert updated is not None
    assert updated.completed_steps == ["A"]
    assert updated.current_step == "B"
    assert updated.progress_percent == pytest.approx(33.33, abs=0.1)
    assert updated.remaining_steps == ["B", "C"]

    progress = runtime.get_progress(mission.id)
    assert progress.completed_count == 1
    assert progress.remaining_count == 2
    assert progress.total_steps == 3


def test_mission_completion(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Complete Test", "Obj", ["A", "B"])
    completed = runtime.complete_mission(mission.id)

    assert completed.state == MissionState.COMPLETED
    assert completed.progress_percent == 100.0
    assert completed.current_step is None
    assert completed.completed_steps == ["A", "B"]
    assert any(entry.event == "mission_completed" for entry in completed.history)
    assert runtime.get_active_mission() is None


def test_mission_failure(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Fail Test", "Obj", ["A"])
    failed = runtime.fail_mission(mission.id, reason="Tool execution blocked")

    assert failed.state == MissionState.FAILED
    assert any(entry.event == "mission_failed" for entry in failed.history)
    assert failed.history[-1].detail == "Tool execution blocked"


def test_mission_resume(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Resume Test", "Obj", ["A", "B"])
    runtime.update_mission(mission.id, state=MissionState.WAITING)

    resumed = runtime.resume_mission(mission.id)
    assert resumed.state == MissionState.RUNNING
    assert any(entry.event == "mission_resumed" for entry in resumed.history)
    assert runtime.get_active_mission() is not None


def test_mission_history(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("History Test", "Obj", ["A", "B"])
    runtime.complete_current_step(mission.id)
    runtime.update_mission(mission.id, priority="HIGH")

    updated = runtime.get_mission(mission.id)
    assert updated is not None
    events = [entry.event for entry in updated.history]
    assert "mission_created" in events
    assert "step_completed" in events
    assert "mission_updated" in events


def test_list_active_missions(runtime: MissionRuntime) -> None:
    first = runtime.create_mission("Active One", "Obj", ["A"])
    second = runtime.create_mission("Active Two", "Obj", ["B"])
    runtime.complete_mission(first.id)

    active = runtime.list_active_missions()
    assert len(active) == 1
    assert active[0].id == second.id


def test_tool_execution_updates_progress(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Tool Test", "Obj", ["Search notes", "Summarize"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    updated = runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=True,
        summary_message="Executed 2 step(s) via obsidian.",
        completed_tool_steps=2,
        failed_tool_steps=0,
    )

    assert updated is not None
    assert updated.state == MissionState.RUNNING
    assert any(
        entry.event == "tool_execution_completed"
        for entry in updated.history
    )


def test_tool_execution_failure_blocks_mission(runtime: MissionRuntime) -> None:
    mission = runtime.create_mission("Blocked Test", "Obj", ["A"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    updated = runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Execution failed.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    assert updated is not None
    assert updated.state == MissionState.BLOCKED


def test_brain_create_mission(brain: Brain) -> None:
    mission = brain.create_mission(
        title="Brain Mission",
        objective="Test Brain API",
        steps=["Plan", "Execute"],
    )

    assert mission.title == "Brain Mission"
    assert brain.list_active_missions()
    assert len(brain.list_active_missions()) >= 1


def test_brain_resume_and_complete_mission(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    mission = brain.create_mission("Lifecycle", "Obj", ["A"])
    brain.update_mission(mission.id, state=MissionState.WAITING)

    resumed = brain.resume_mission(mission.id)
    assert resumed.state == MissionState.RUNNING

    completed = brain.complete_mission(mission.id)
    assert completed.state == MissionState.COMPLETED
    assert brain.list_active_missions() == []


def test_brain_execute_request_updates_mission(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    mission = brain.create_mission("Tool Hook", "Obj", ["Run tools"])
    brain.update_mission(mission.id, state=MissionState.RUNNING)

    brain.tool_intelligence.plan = MagicMock(
        return_value=brain.tool_intelligence.plan("hello"),
    )
    mock_execution = MagicMock()
    mock_execution.success = True
    mock_execution.summary_message = "No tools required."
    mock_execution.completed_steps = ()
    mock_execution.failed_steps = ()
    brain.tool_execution_engine.execute = MagicMock(return_value=mock_execution)

    brain.execute_request("hello")

    updated = brain.mission_manager.runtime.get_mission(mission.id)
    assert updated is not None
    assert any(
        entry.event == "tool_execution_completed"
        for entry in updated.history
    )


def test_brain_mission_progress(brain: Brain) -> None:
    mission = brain.create_mission("Progress API", "Obj", ["A", "B"])
    brain.mission_manager.runtime.complete_current_step(mission.id)

    progress = brain.get_mission_progress(mission.id)
    assert progress.completed_count == 1
    assert progress.progress_percent == pytest.approx(50.0, abs=0.1)


def test_cognitive_loop_observes_active_mission(brain: Brain) -> None:
    brain.create_mission("Cognitive", "Obj", ["Step 1"])
    result = brain.generate_thoughts("What is next?")

    mission_observations = [
        obs for obs in result.observations if obs.source == "mission"
    ]
    assert mission_observations
    assert "Cognitive" in mission_observations[0].summary

    mission_thoughts = [thought for thought in result.thoughts if thought.source == "mission"]
    assert mission_thoughts


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    return Brain(
        agent_manager=AgentManager(
            memory_service=MemoryService(
                short_term=MemoryManager(),
                long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
            ),
        ),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=MemoryService(
            short_term=MemoryManager(),
            long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
        ),
        tool_manager=ToolManager(project_root=tmp_path),
        conversation_engine=ConversationEngine(persist_sessions=False),
        llm=mock_llm,
    )

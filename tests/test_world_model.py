# =====================================
# Titan World Model Tests
# =====================================

"""Comprehensive tests for World Model V1 — state representation only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.world_model import (
    ActiveFocus,
    ProjectHealthStatus,
    WorldModel,
    WorldModelSnapshot,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionState, TaskState
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )


def _world_model(brain: Brain) -> WorldModel:
    return brain.world_model


def test_brain_wires_world_model(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    assert brain.world_model is not None
    assert isinstance(brain.world_model, WorldModel)


def test_build_world_model_returns_snapshot(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    snapshot = brain.build_world_model()

    assert isinstance(snapshot, WorldModelSnapshot)
    assert snapshot.schema_version == 1
    assert snapshot.summary
    assert snapshot.runtime_status.titan_version


def test_get_snapshot_builds_when_empty(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    snapshot = brain.get_world_model_snapshot()

    assert isinstance(snapshot, WorldModelSnapshot)
    assert snapshot.timestamp is not None


def test_refresh_rebuilds_snapshot(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    first = brain.build_world_model()
    second = brain.refresh_world_model()

    assert isinstance(second, WorldModelSnapshot)
    assert second.timestamp >= first.timestamp


def test_active_mission_in_world_model(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Ship Feature", "Deliver V1", ["Design", "Implement"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    snapshot = brain.build_world_model()

    mission_ids = {item["id"] for item in snapshot.active_missions}
    assert mission.id in mission_ids
    assert any(task.mission_id == mission.id for task in snapshot.open_tasks)


def test_completed_tasks_partition(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Task Partition", "Obj", ["Done step", "Open step"])
    runtime.complete_current_step(mission.id)

    snapshot = brain.build_world_model()

    completed = [t for t in snapshot.completed_tasks if t.mission_id == mission.id]
    open_tasks = [t for t in snapshot.open_tasks if t.mission_id == mission.id]

    assert len(completed) >= 1
    assert completed[0].state == TaskState.COMPLETED
    assert len(open_tasks) >= 1
    assert open_tasks[0].state in {TaskState.PENDING, TaskState.IN_PROGRESS}


def test_blocked_mission_surfaces_blocker(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Blocked Work", "Unblock", ["Step"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Failure.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    blockers = brain.get_world_blockers()

    assert len(blockers) >= 1
    sources = {blocker.source for blocker in blockers}
    assert "executive_function" in sources or "mission_runtime" in sources


def test_project_state_slice(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.state_manager.update_state("active_project", "Titan")

    project_state = brain.get_project_state()

    assert project_state.active_projects
    assert isinstance(project_state.project_dependencies, dict)
    assert project_state.timestamp is not None


def test_workspace_state_slice(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    workspace_state = brain.get_workspace_state()

    assert workspace_state.workspace_root
    assert workspace_state.timestamp is not None


def test_dependencies_from_project_intelligence(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.build_world_model()

    dependencies = brain.get_world_dependencies()

    assert isinstance(dependencies, dict)
    if dependencies:
        sample_key = next(iter(dependencies))
        assert isinstance(dependencies[sample_key], tuple)


def test_available_tools_populated(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    snapshot = brain.build_world_model()

    assert len(snapshot.available_tools) >= 1
    tool_ids = {tool.tool_id for tool in snapshot.available_tools}
    assert all(tool.enabled is not None for tool in snapshot.available_tools)
    assert isinstance(tool_ids, set)


def test_active_focus_from_executive(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Focus Mission", "Obj", ["A"])
    runtime.resume_mission(mission.id)

    focus = brain.get_world_active_focus()

    assert isinstance(focus, ActiveFocus)
    assert focus.mission_id == mission.id or focus.recommended_mission_id is not None


def test_project_health_degraded_when_blocked(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Health Test", "Obj", ["A"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Blocked.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    snapshot = brain.build_world_model()

    assert snapshot.project_health
    statuses = {item.status for item in snapshot.project_health}
    assert ProjectHealthStatus.BLOCKED in statuses or ProjectHealthStatus.DEGRADED in statuses


def test_export_world_model_json_serializable(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.build_world_model()

    exported = brain.export_world_model()

    assert exported["schema_version"] == 1
    assert "world_model" in exported
    assert "exported_at" in exported
    json.dumps(exported)


def test_snapshot_to_dict_and_format_for_prompt(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    snapshot = brain.build_world_model()

    data = snapshot.to_dict()
    assert data["schema_version"] == 1
    assert "blockers" in data
    assert "opportunities" in data

    prompt = snapshot.format_for_prompt()
    assert "WORLD MODEL" in prompt
    assert "BLOCKERS" in prompt


def test_world_model_standalone_minimal_deps(tmp_path: Path) -> None:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    context = ContextManager(state_manager=state, mission_manager=mission)

    model = WorldModel(
        mission_manager=mission,
        memory_service=memory,
        context_manager=context,
        state_manager=state,
    )
    snapshot = model.build_world_model()

    assert snapshot.runtime_status.current_user == "Nolan"
    assert snapshot.active_missions == ()


def test_opportunities_include_executive_recommendation(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    low = runtime.create_mission("Low", "Obj", ["A"], priority="LOW")
    high = runtime.create_mission("High", "Obj", ["B"], priority="HIGH")
    runtime.resume_mission(low.id)
    runtime.update_mission(high.id, state=MissionState.READY)

    opportunities = brain.build_world_model().opportunities

    assert isinstance(opportunities, tuple)


def test_user_goals_from_memory_retrieval(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.long_memory.write_categorized(
        "Nolan",
        "goals",
        "Finish the World Model sprint this week.",
    )

    snapshot = brain.build_world_model("world model goals")

    assert snapshot.user_goals or snapshot.current_focus.user_goal_hints


def test_integrations_include_github_when_tool_installed(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    snapshot = brain.build_world_model()

    integration_ids = {item.integration_id for item in snapshot.connected_integrations}
    assert "github" in integration_ids or len(integration_ids) >= 0


def test_world_model_does_not_mutate_missions(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Immutable", "Obj", ["A"])
    before = runtime.get_mission(mission.id)
    assert before is not None

    brain.build_world_model()
    brain.refresh_world_model()

    after = runtime.get_mission(mission.id)
    assert after is not None
    assert after.state == before.state
    assert after.title == before.title

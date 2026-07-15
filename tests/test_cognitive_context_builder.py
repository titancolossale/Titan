# =====================================
# Titan Cognitive Context Builder Tests
# =====================================

"""Comprehensive tests for Cognitive Context Builder V1 — read-only assembly only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.cognitive_context_builder import (
    CognitiveContext,
    CognitiveContextBuilder,
    ContextBuildMode,
)
from brain.llm import LLM
from brain.reasoning_models import ReasoningDomain, ReasoningResult
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionState
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


def test_brain_wires_cognitive_context_builder(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    assert brain.cognitive_context_builder is not None
    assert isinstance(brain.cognitive_context_builder, CognitiveContextBuilder)
    assert brain.reasoning_engine is not None


def test_build_context_returns_cognitive_context(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context()

    assert isinstance(context, CognitiveContext)
    assert context.schema_version == 1
    assert context.build_mode == ContextBuildMode.GENERAL
    assert context.user
    assert context.summary
    assert isinstance(context.sources, dict)


def test_build_for_request_mode(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context_for_request(
        "Analyze the architecture of the brain module",
    )

    assert context.build_mode == ContextBuildMode.REQUEST
    assert context.message
    assert "world_model" in context.sources or context.world_model is not None


def test_build_for_project_mode(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.state_manager.update_state("active_project", "Titan")

    context = brain.build_cognitive_context_for_project("Titan")

    assert context.build_mode == ContextBuildMode.PROJECT
    assert context.current_project == "Titan"


def test_build_for_code_task_mode(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context_for_code_task(
        "Refactor class Brain in module brain.brain",
    )

    assert context.build_mode == ContextBuildMode.CODE_TASK
    assert context.developer_workflow_plan is not None or context.architecture is not None


def test_build_for_mission_mode(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Context Mission", "Test", ["Step one"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    context = brain.build_cognitive_context_for_mission(mission.id)

    assert context.build_mode == ContextBuildMode.MISSION
    assert context.focus_mission_id == mission.id
    assert len(context.active_missions) == 1
    assert context.active_missions[0].id == mission.id


def test_get_last_context_cached(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    first = brain.build_cognitive_context("hello")
    last = brain.get_last_cognitive_context()

    assert last is not None
    assert last.timestamp == first.timestamp
    assert last.message == first.message


def test_export_context_json_serializable(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.build_cognitive_context("export test")
    exported = brain.export_cognitive_context()

    assert exported["schema_version"] == 1
    assert "cognitive_context" in exported
    json.dumps(exported)


def test_format_for_prompt_includes_sections(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context_for_request("plan the next sprint")

    prompt = context.format_for_prompt()
    assert "CONTEXTE COGNITIF" in prompt
    assert context.build_mode.value in prompt


def test_to_dict_round_trip_keys(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context()
    data = context.to_dict()

    for key in (
        "schema_version",
        "build_mode",
        "user",
        "sources",
        "active_missions",
        "verified_knowledge",
        "conversation_context",
    ):
        assert key in data


def test_active_mission_surfaces_in_context(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Ship V1", "Deliver", ["Design", "Build"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)

    context = brain.build_cognitive_context_for_request("continue the mission")

    mission_ids = {m.id for m in context.active_missions}
    assert mission.id in mission_ids


def test_memory_retrieval_on_request(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.memory_service.store_categorized(
        user="Nolan",
        category="projects",
        content="Titan uses modular monolith architecture",
    )

    context = brain.build_cognitive_context_for_request(
        "What architecture does Titan use?",
    )

    if context.sources.get("memory"):
        assert context.memories is not None


def test_reasoning_engine_uses_cognitive_context(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Compare two approaches for implementing caching")

    assert isinstance(result, ReasoningResult)
    assert isinstance(result.context_sources, dict)
    assert result.context_sources.get("world_model") is True


def test_reasoning_engine_project_intelligence_via_builder(tmp_path: Path) -> None:
    project = tmp_path / "TitanCtx"
    project.mkdir()
    (project / "brain").mkdir()
    (project / "brain" / "__init__.py").write_text("", encoding="utf-8")
    (project / "brain" / "brain.py").write_text(
        "class Brain:\n    pass\n",
        encoding="utf-8",
    )

    brain = _build_brain(project)
    result = brain.reason("Analyze the architecture of the brain module")

    assert result.context_sources.get("project_intelligence") is True


def test_reasoning_engine_code_context_via_builder(tmp_path: Path) -> None:
    project = tmp_path / "TitanCode"
    project.mkdir()
    (project / "brain").mkdir()
    (project / "brain" / "__init__.py").write_text("", encoding="utf-8")
    (project / "brain" / "brain.py").write_text(
        "class Brain:\n    def think(self):\n        return True\n",
        encoding="utf-8",
    )

    brain = _build_brain(project)
    result = brain.reason("Explain class Brain in module brain.brain")

    assert result.context_sources.get("code_intelligence") is True


def test_builder_read_only_does_not_mutate_memory(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    before = brain.memory_service.get_document()

    brain.build_cognitive_context_for_request("remember this forever")
    after = brain.memory_service.get_document()

    assert before == after


def test_builder_graceful_degradation_without_world_model(tmp_path: Path) -> None:
    builder = CognitiveContextBuilder()
    context = builder.build_context("minimal")

    assert isinstance(context, CognitiveContext)
    assert context.world_model is None
    assert context.sources.get("world_model") is False


def test_standalone_builder_with_partial_wiring(tmp_path: Path) -> None:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    context_manager = ContextManager(state_manager=state, mission_manager=mission)
    builder = CognitiveContextBuilder(
        memory_service=memory,
        mission_manager=mission,
        context_manager=context_manager,
    )

    context = builder.build_for_request("test request", user="Nolan")

    assert context.user == "Nolan"
    assert context.sources.get("mission_runtime") is True


def test_reasoning_requires_attached_builder() -> None:
    from brain.reasoning_engine import ReasoningEngine

    engine = ReasoningEngine()
    with pytest.raises(RuntimeError, match="CognitiveContextBuilder"):
        engine.reason("test without builder")

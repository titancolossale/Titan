# =====================================
# Titan Autonomy Integration Tests
# =====================================

"""Integration tests for Phase 9 autonomy pipeline wiring (P9-090)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.autonomy_policy import AutonomyPolicy, ProactiveLevel
from brain.brain import Brain
from brain.initiative_engine import InitiativeEngine
from memory.learning_memory import LearningMemory


@pytest.fixture
def autonomy_brain(tmp_path: Path, mock_agent_llm: MagicMock) -> Brain:
    """Brain with proactive autonomy enabled for pipeline tests."""
    from agents.agent_manager import AgentManager
    from agents.agent_llm import AgentLLM
    from brain.llm import LLM
    from context.context_manager import ContextManager
    from core.conversation_engine import ConversationEngine
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from tools.tool_manager import ToolManager

    policy = AutonomyPolicy(proactive_level=ProactiveLevel.MEDIUM)
    learning = LearningMemory(file_path=tmp_path / "learning.json")
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."

    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )

    return Brain(
        agent_manager=AgentManager(
            agent_llm=mock_agent_llm,
            memory_service=memory,
            autonomy_policy=policy,
        ),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        conversation_engine=ConversationEngine(persist_sessions=False),
        llm=mock_llm,
        autonomy_policy=policy,
        learning_memory=learning,
        initiative_engine=InitiativeEngine(policy=policy, learning_memory=learning),
    )


def test_initiative_in_prompt_when_proactive_enabled(autonomy_brain: Brain) -> None:
    """INITIATIVE section appears when policy allows and signals detected."""
    autonomy_brain.think("c'est urgent, deadline demain")

    prompt_sent = autonomy_brain.llm.ask.call_args[0][0]
    assert "INITIATIVE" in prompt_sent


def test_initiative_absent_when_policy_off(tmp_path: Path, mock_agent_llm: MagicMock) -> None:
    """Disabled proactive policy excludes INITIATIVE from prompt."""
    from agents.agent_manager import AgentManager
    from brain.llm import LLM
    from context.context_manager import ContextManager
    from core.conversation_engine import ConversationEngine
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from tools.tool_manager import ToolManager

    policy = AutonomyPolicy(proactive_level=ProactiveLevel.OFF)
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse."
    state = StateManager(file_path=tmp_path / "state.json")
    mission = MissionManager(file_path=tmp_path / "mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "ltm.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(agent_llm=mock_agent_llm, memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        conversation_engine=ConversationEngine(persist_sessions=False),
        llm=mock_llm,
        autonomy_policy=policy,
        initiative_engine=InitiativeEngine(policy=policy),
    )

    brain.think("deadline urgent")
    prompt_sent = brain.llm.ask.call_args[0][0]
    assert "INITIATIVE" not in prompt_sent

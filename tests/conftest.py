# =====================================

# Titan Test Fixtures

# =====================================



"""Pytest fixtures for JSON-backed managers using isolated temporary paths."""



from __future__ import annotations



from pathlib import Path

from unittest.mock import MagicMock



import pytest



from agents.agent_llm import AgentLLM
from agents.agent_manager import AgentManager

from brain.brain import Brain

from brain.llm import LLM

from context.context_manager import ContextManager

from core.conversation_engine import ConversationEngine
from core.mission_manager import MissionManager

from core.state_manager import StateManager

from memory.long_term_memory import LongTermMemory

from memory.memory_manager import MemoryManager

from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager





@pytest.fixture

def state_manager(tmp_path: Path) -> StateManager:

    """StateManager pointed at a temp file; never reads or writes repo data/."""

    return StateManager(file_path=tmp_path / "titan_state.json")





@pytest.fixture

def mission_manager(tmp_path: Path) -> MissionManager:

    """MissionManager pointed at a temp file; never reads or writes repo data/."""

    return MissionManager(file_path=tmp_path / "titan_mission.json")





@pytest.fixture

def long_term_memory(tmp_path: Path) -> LongTermMemory:

    """LongTermMemory pointed at a temp file; never reads or writes repo data/."""

    return LongTermMemory(file_path=tmp_path / "long_term_memory.json")





@pytest.fixture

def memory_service(tmp_path: Path) -> MemoryService:

    """MemoryService with isolated long-term JSON (P3-040)."""

    return MemoryService(

        short_term=MemoryManager(),

        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),

    )





@pytest.fixture

def mock_agent_llm() -> MagicMock:

    """Mock AgentLLM — no live OpenAI calls during agent orchestration (P5-042)."""

    mock = MagicMock(spec=AgentLLM)
    mock.ask.return_value = (
        "Résumé : Analyse interne mock.\n\n"
        "Artefacts:\n"
        "```python\n"
        "def example():\n"
        "    return True\n"
        "```"
    )
    return mock





@pytest.fixture

def brain(tmp_path: Path, mock_agent_llm: MagicMock) -> Brain:

    """Brain with temp JSON paths and mocked LLM — no live OpenAI calls (P1-060)."""

    mock_llm = MagicMock(spec=LLM)

    mock_llm.ask.return_value = "Réponse de test."



    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    conversation_engine = ConversationEngine(persist_sessions=False)

    return Brain(

        agent_manager=AgentManager(
            agent_llm=mock_agent_llm,
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

        conversation_engine=conversation_engine,

        llm=mock_llm,

    )


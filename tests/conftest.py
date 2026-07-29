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
from core.goal_manager import GoalManager
from core.mission_manager import MissionManager
from core.project_manager import ProjectManager

from core.state_manager import StateManager

from memory.long_term_memory import LongTermMemory

from memory.memory_manager import MemoryManager

from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


@pytest.fixture(autouse=True)
def _isolate_voice_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent local production enrollment activation from leaking into tests.

    Host Phase 20.10B-1 writes production flags into ``.env``. ``load_dotenv``
    can re-apply those values after a bare ``delenv``, so tests force explicit
    development defaults instead.
    """
    # Import settings first (may call load_dotenv), then override.
    try:
        from config import settings as app_settings
    except Exception:
        app_settings = None

    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_PROVIDER", "histogram")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_VERSION", "histogram_v1")
    monkeypatch.setenv("TITAN_VOICE_BIOMETRIC_TRUST_MODE", "development")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST", "false")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY", "true")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "false")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO", "false")
    monkeypatch.setenv("TITAN_VOICE_EMBEDDING_KEY_ID", "primary")
    monkeypatch.delenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", raising=False)

    if app_settings is not None:
        monkeypatch.setattr(app_settings, "TITAN_VOICE_EMBEDDING_PROVIDER", "histogram")
        monkeypatch.setattr(app_settings, "TITAN_VOICE_EMBEDDING_VERSION", "histogram_v1")
        monkeypatch.setattr(app_settings, "TITAN_VOICE_BIOMETRIC_TRUST_MODE", "development")
        monkeypatch.setattr(
            app_settings, "TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST", False
        )
        monkeypatch.setattr(
            app_settings, "TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY", True
        )
        monkeypatch.setattr(app_settings, "TITAN_VOICE_EMBEDDING_ENCRYPTION", False)
        monkeypatch.setattr(app_settings, "TITAN_VOICE_EMBEDDING_KEY_ID", "primary")
        monkeypatch.setattr(
            app_settings, "TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO", False
        )

    try:
        from voice.embedding_provider import (
            reset_embedding_registry_for_tests,
            set_embedding_provider,
        )

        reset_embedding_registry_for_tests()
        set_embedding_provider(None)
        yield
        reset_embedding_registry_for_tests()
        set_embedding_provider(None)
    except Exception:
        yield


@pytest.fixture

def state_manager(tmp_path: Path) -> StateManager:

    """StateManager pointed at a temp file; never reads or writes repo data/."""

    return StateManager(file_path=tmp_path / "titan_state.json")





@pytest.fixture

def goal_manager(tmp_path: Path, state_manager: StateManager) -> GoalManager:

    """GoalManager pointed at a temp file; mirrors into the test StateManager."""

    return GoalManager(
        file_path=tmp_path / "titan_goals.json",
        state_manager=state_manager,
    )





@pytest.fixture

def project_manager(
    tmp_path: Path,
    state_manager: StateManager,
    goal_manager: GoalManager,
) -> ProjectManager:

    """ProjectManager pointed at a temp file; mirrors into the test StateManager."""

    manager = ProjectManager(
        file_path=tmp_path / "titan_projects.json",
        state_manager=state_manager,
        goal_manager=goal_manager,
    )
    goal_manager.bind_project_manager(manager)
    return manager





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
    goals = GoalManager(
        file_path=tmp_path / "titan_goals.json",
        state_manager=state,
    )
    projects = ProjectManager(
        file_path=tmp_path / "titan_projects.json",
        state_manager=state,
        goal_manager=goals,
    )
    mission = MissionManager(
        file_path=tmp_path / "titan_mission.json",
        state_manager=state,
        project_manager=projects,
    )
    goals.bind_project_manager(projects)
    goals.bind_mission_manager(mission)
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

        project_manager=projects,

        goal_manager=goals,

        memory_service=MemoryService(

            short_term=MemoryManager(),

            long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),

        ),

        tool_manager=ToolManager(project_root=tmp_path),

        conversation_engine=conversation_engine,

        llm=mock_llm,

    )


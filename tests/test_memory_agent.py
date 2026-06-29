# =====================================
# Titan Memory Agent Tests
# =====================================

"""Tests for Memory Agent v1 (Phase 5 — P5-050–P5-051)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.memory_agent import MemoryAgent
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService


@pytest.fixture
def memory_service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )


@pytest.fixture
def mock_agent_llm() -> MagicMock:
    mock = MagicMock(spec=AgentLLM)
    mock.ask.return_value = (
        "Résumé : Session productive sur Titan.\n\n"
        "Notes candidates :\n"
        "[preferences] Nolan préfère Python pour Titan\n"
        "[projects] Phase 5 agent framework en cours"
    )
    return mock


def test_memory_agent_persists_categorized_notes(
    memory_service: MemoryService,
    mock_agent_llm: MagicMock,
) -> None:
    """P5-050: Memory Agent writes parsed [category] notes to long-term memory."""
    memory_service.remember_session("Discussion sur Python et Phase 5")
    agent = MemoryAgent(memory_service, agent_llm=mock_agent_llm)
    ctx = AgentContext(user_message="résume la session", task="Résumer session")

    result = agent.execute("Résumer session", ctx)

    assert "persistée" in result.summary.lower() or "persistée" in result.result.lower()
    doc = memory_service.get_document()
    nolan = doc["users"]["Nolan"]
    assert any("Python" in pref for pref in nolan.get("preferences", []))
    assert any("Phase 5" in proj for proj in nolan.get("projects", []))


def test_memory_agent_empty_session_returns_message(
    memory_service: MemoryService,
    mock_agent_llm: MagicMock,
) -> None:
    """P5-050: no session notes → graceful message, no LLM call."""
    agent = MemoryAgent(memory_service, agent_llm=mock_agent_llm)
    ctx = AgentContext(user_message="résume la session", task="Résumer")

    result = agent.execute("Résumer", ctx)

    assert "aucune note" in result.summary.lower()
    mock_agent_llm.ask.assert_not_called()


def test_memory_route_registered_in_registry() -> None:
    """P5-051: memory keywords route to memory agent pipeline."""
    from agents.agent_registry import default_registry

    tasks = default_registry.create_tasks("résume la session")
    assert tasks == [("memory", "Résumer les notes de session pour : résume la session")]
    assert default_registry.select_agent("résume la session") == "memory"


def test_agent_manager_registers_memory_when_service_provided(
    memory_service: MemoryService,
) -> None:
    """P5-051: AgentManager registers memory agent with MemoryService injection."""
    from agents.agent_manager import AgentManager

    manager = AgentManager(memory_service=memory_service)

    assert "memory" in manager.list_agents()
    assert manager.get_agent("memory") is not None

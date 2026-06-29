# =====================================
# Titan Composition / DI Guard Tests
# =====================================

"""Automated guards that shared managers are wired once from the composition root."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.brain import Brain
from core.titan import Titan

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_MANAGER_CONSTRUCTORS = (
    "AgentManager()",
    "ContextManager()",
    "StateManager()",
    "MissionManager()",
    "LongTermMemory()",
    "MemoryService()",
    "ToolManager()",
)


def test_titan_and_brain_share_agent_manager() -> None:
    """Titan must inject its AgentManager into Brain (P1-052); no duplicate instance."""
    titan = Titan()

    assert titan.agents is titan.brain.agent_manager


def test_agent_manager_identity_through_orchestrator_chain() -> None:
    """Injected AgentManager must reach TaskManager and TaskOrchestrator unchanged."""
    titan = Titan()
    shared = titan.agents

    assert titan.brain.task_manager.agent_manager is shared
    assert titan.brain.task_orchestrator.agent_manager is shared


def test_titan_and_brain_share_context_manager() -> None:
    """Titan must inject its ContextManager into Brain (P1-054); no duplicate instance."""
    titan = Titan()

    assert titan.context is titan.brain.context_manager


def test_titan_and_brain_share_state_manager() -> None:
    """Titan must inject its StateManager into Brain (P1-056); no duplicate instance."""
    titan = Titan()

    assert titan.state is titan.brain.state_manager


def test_titan_and_brain_share_mission_manager() -> None:
    """Titan must inject its MissionManager into Brain (P1-057); no duplicate instance."""
    titan = Titan()

    assert titan.mission is titan.brain.mission_manager


def test_titan_and_brain_share_memory_service() -> None:
    """Titan must inject its MemoryService into Brain (P3-040); no duplicate instance."""
    titan = Titan()

    assert titan.memory is titan.brain.memory_service
    assert titan.long_memory is titan.brain.long_memory
    assert titan.long_memory is titan.memory.long_term


def test_titan_and_brain_share_long_term_memory() -> None:
    """Long-term store is owned by MemoryService at composition root (P3-040)."""
    titan = Titan()

    assert titan.memory.get_long_term() is titan.long_memory.get_memory()
    assert titan.long_memory is titan.brain.long_memory


def test_brain_fixture_constructs_without_api_call(brain: Brain) -> None:
    """P1-060 factory fixture must build Brain with mocked LLM."""
    assert brain.llm.ask("test") == "Réponse de test."


def _brain_implementation_source() -> str:
    """Return Brain class source after the class docstring (excludes design examples)."""
    path = PROJECT_ROOT / "brain" / "brain.py"
    text = path.read_text(encoding="utf-8")
    class_idx = text.index("class Brain:")
    doc_start = text.index('"""', class_idx)
    doc_end = text.index('"""', doc_start + 3) + 3
    return text[doc_end:]


def test_brain_has_no_duplicate_manager_constructors() -> None:
    """P1-061: Brain implementation must not instantiate shared managers."""
    impl_source = _brain_implementation_source()

    for pattern in _FORBIDDEN_MANAGER_CONSTRUCTORS:
        assert pattern not in impl_source, (
            f"Forbidden {pattern} found in Brain implementation (expected only in Titan)"
        )


def test_titan_and_brain_share_tool_manager() -> None:
    """Titan must inject its ToolManager into Brain (P6-036); no duplicate instance."""
    titan = Titan()

    assert titan.tools is titan.brain.tool_manager


def test_titan_and_brain_share_conversation_engine() -> None:
    """Titan must inject its ConversationEngine into Brain (P7-032); no duplicate instance."""
    titan = Titan()

    assert titan.conversation.engine is titan.brain.conversation_engine


def test_titan_wires_autonomy_subsystems() -> None:
    """Titan composition root owns scheduler, learning memory, and policy (P9-090)."""
    titan = Titan()

    assert titan.autonomy_policy is titan.brain.autonomy_policy
    assert titan.learning_memory is titan.brain.learning_memory
    assert titan.scheduler is not None
    assert titan.job_runner is not None
    assert "web" in titan.agents.list_agents()
    assert "automation" in titan.agents.list_agents()


def test_brain_requires_injected_managers() -> None:
    """P1-059: Brain() without keyword args must fail fast."""
    with pytest.raises(TypeError):
        Brain()  # type: ignore[call-arg]

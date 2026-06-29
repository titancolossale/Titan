# =====================================
# Titan LLM-Backed Agent Tests
# =====================================

"""Tests for LLM-backed specialist agents with mocked AgentLLM (P5-040–P5-042)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.agent_manager import AgentManager
from agents.agent_response_parser import parse_agent_output
from agents.coding_agent import CodingAgent
from agents.general_agent import GeneralAgent
from agents.planning_agent import PlanningAgent
from agents.reasoning_agent import ReasoningAgent
from agents.research_agent import ResearchAgent


@pytest.fixture
def mock_agent_llm() -> MagicMock:
    mock = MagicMock(spec=AgentLLM)
    mock.ask.return_value = (
        "Résumé : Fonction sum proposée.\n\n"
        "```python\n"
        "def sum(a, b):\n"
        "    return a + b\n"
        "```"
    )
    return mock


@pytest.fixture
def agent_context() -> AgentContext:
    return AgentContext(
        user_message="Code une fonction sum",
        task="Écrire une solution de code pour : sum",
        current_user="Nolan",
    )


def test_parse_agent_output_extracts_code_blocks() -> None:
    """P5-040: parser extracts code blocks as artifacts."""
    raw = "Résumé : test\n\n```python\ndef foo():\n    pass\n```"
    result = parse_agent_output("coding", "task", raw)

    assert "test" in result.summary.lower() or "Résumé" in result.summary
    assert result.artifacts
    assert "def foo" in result.artifacts[0]


def test_parse_agent_output_empty_returns_zero_confidence() -> None:
    """P5-040: empty LLM output degrades gracefully."""
    result = parse_agent_output("coding", "task", "   ")

    assert result.confidence == 0.0


@pytest.mark.parametrize(
    ("agent_cls", "agent_key"),
    [
        (CodingAgent, "coding"),
        (ResearchAgent, "research"),
        (PlanningAgent, "planning"),
        (ReasoningAgent, "reasoning"),
        (GeneralAgent, "base"),
    ],
)
def test_llm_agents_call_scoped_llm(
    agent_cls,
    agent_key: str,
    mock_agent_llm: MagicMock,
    agent_context: AgentContext,
) -> None:
    """P5-041: all core agents delegate to AgentLLM."""
    agent = agent_cls(agent_llm=mock_agent_llm)
    result = agent.execute("Task test", agent_context)

    mock_agent_llm.ask.assert_called_once_with(agent_key, "Task test", agent_context)
    assert result.agent_name == agent_key
    assert result.summary


def test_coding_agent_extracts_artifacts_from_mock_llm(
    mock_agent_llm: MagicMock,
    agent_context: AgentContext,
) -> None:
    """P5-041: coding agent parses code blocks from LLM response."""
    agent = CodingAgent(agent_llm=mock_agent_llm)
    result = agent.execute("Écrire sum", agent_context)

    assert any("def sum" in artifact for artifact in result.artifacts)


def test_agent_manager_wires_shared_agent_llm(mock_agent_llm: MagicMock) -> None:
    """P5-042: AgentManager shares one AgentLLM across all specialists."""
    manager = AgentManager(agent_llm=mock_agent_llm)
    ctx = AgentContext(user_message="test", task="task")

    manager.execute("coding", "code task", ctx)
    manager.execute("research", "research task", ctx)

    assert mock_agent_llm.ask.call_count == 2


def test_brain_orchestration_uses_mock_agent_llm(brain, mock_agent_llm: MagicMock) -> None:
    """P5-042: Brain think() triggers agent LLM calls without live API."""
    brain.think("test code python")

    assert mock_agent_llm.ask.call_count >= 1
    assert brain.llm.ask.call_count == 1

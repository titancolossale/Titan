# =====================================
# Titan Agent LLM Tests
# =====================================

"""Tests for scoped agent LLM calls (Phase 5 — P5-030–P5-031)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from brain.llm import LLM


@pytest.fixture
def agent_context() -> AgentContext:
    return AgentContext(
        user_message="Écris une fonction Python",
        task="Écrire une solution de code pour : test",
        current_user="Nolan",
        active_project="Titan",
    )


def test_load_instructions_reads_agent_prompt(tmp_path: Path) -> None:
    """P5-030: agent prompts load from prompts/agents/."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "coding.md").write_text("Instructions coding test", encoding="utf-8")

    agent_llm = AgentLLM(prompts_dir=tmp_path)
    instructions = agent_llm.load_instructions("coding")

    assert "Instructions coding test" in instructions


def test_load_instructions_falls_back_for_unknown_agent(tmp_path: Path) -> None:
    """P5-030: unknown agent key uses base prompt."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "base.md").write_text("Base agent instructions", encoding="utf-8")

    agent_llm = AgentLLM(prompts_dir=tmp_path)
    instructions = agent_llm.load_instructions("unknown_agent")

    assert "Base agent instructions" in instructions


def test_ask_uses_scoped_instructions_with_llm(
    agent_context: AgentContext,
) -> None:
    """P5-031: AgentLLM calls ask_scoped, not full Titan constitution."""
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask_scoped.return_value = "Résumé interne coding."

    agent_llm = AgentLLM(llm=mock_llm)
    with patch.object(agent_llm, "load_instructions", return_value="Scoped coding only"):
        result = agent_llm.ask("coding", "Écrire sum()", agent_context)

    assert result == "Résumé interne coding."
    mock_llm.ask_scoped.assert_called_once()
    call_args = mock_llm.ask_scoped.call_args
    assert call_args[0][1] == "Scoped coding only"
    assert "Écrire sum()" in call_args[0][0]


def test_ask_with_mock_provider_prepends_instructions(
    agent_context: AgentContext,
) -> None:
    """P5-031: non-LLM providers receive instructions in prompt."""
    mock_provider = MagicMock()
    mock_provider.ask.return_value = "Provider response"

    agent_llm = AgentLLM(llm=mock_provider)
    with patch.object(agent_llm, "load_instructions", return_value="Agent rules"):
        result = agent_llm.ask("research", "Chercher docs", agent_context)

    assert result == "Provider response"
    prompt_sent = mock_provider.ask.call_args[0][0]
    assert "Agent rules" in prompt_sent
    assert "Chercher docs" in prompt_sent


def test_build_prompt_includes_context_block(agent_context: AgentContext) -> None:
    """P5-031: agent prompt includes operational context."""
    agent_llm = AgentLLM(llm=MagicMock())
    prompt = agent_llm.build_prompt("Task interne", agent_context)

    assert "Nolan" in prompt
    assert "Titan" in prompt
    assert "Task interne" in prompt
    assert "Écris une fonction Python" in prompt

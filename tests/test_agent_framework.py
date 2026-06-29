# =====================================
# Titan Agent Framework Tests
# =====================================

"""Tests for AgentResult, AgentContext, and structured execution (P5-020–P5-023)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.agent_context import AgentContext
from agents.agent_result import AgentResult
from agents.agent_manager import AgentManager
from agents.coding_agent import CodingAgent
from brain.pipeline.context_bundle import ThinkContext
from context.models import ContextSnapshot


def test_agent_result_result_property_formats_summary_and_artifacts() -> None:
    """P5-020: result property produces prompt-ready text."""
    result = AgentResult(
        agent_name="coding",
        task="Écrire une fonction",
        summary="Fonction addition proposée.",
        artifacts=["def add(a, b): return a + b"],
        tools_used=["file_read"],
        confidence=0.8,
    )
    text = result.result

    assert "Fonction addition proposée." in text
    assert "def add(a, b)" in text
    assert "file_read" in text
    assert "80%" in text


def test_agent_result_from_text_wraps_legacy_output() -> None:
    """P5-020: from_text preserves backward compatibility."""
    result = AgentResult.from_text("coding", "task", "legacy output")

    assert result.summary == "legacy output"
    assert result.agent_name == "coding"


def test_agent_context_from_think_context() -> None:
    """P5-021: AgentContext extracts fields from ThinkContext."""
    snapshot = ContextSnapshot(
        current_user="Ibrahim",
        active_project="Trading Bot",
        current_goal="Backtest strategy",
        current_phase="Phase 5",
        session_id="sess-1",
        mode="dev",
        last_action="none",
        mission_active=True,
        mission_title="Trading mission",
    )
    think_ctx = ThinkContext(
        user_message="Code un indicateur RSI",
        current_user="Ibrahim",
        context_snapshot=snapshot,
        situational_context="Contexte Ibrahim",
        retrieved_memory="Préfère Python",
        state={"active_project": "Trading Bot"},
        mission={"active": True, "title": "Trading mission"},
        executive_analysis="Priorité : indicateurs",
    )

    agent_ctx = AgentContext.from_think_context(think_ctx, task="Écrire RSI")

    assert agent_ctx.current_user == "Ibrahim"
    assert agent_ctx.active_project == "Trading Bot"
    assert agent_ctx.task == "Écrire RSI"
    assert "Contexte Ibrahim" in agent_ctx.prompt_block()


def test_agent_manager_execute_returns_structured_result(mock_agent_llm: MagicMock) -> None:
    """P5-023: execute() always returns AgentResult."""
    manager = AgentManager(agent_llm=mock_agent_llm)
    result = manager.execute("coding", "Écrire une fonction sum")

    assert isinstance(result, AgentResult)
    assert result.agent_name == "coding"
    assert result.summary


def test_coding_agent_returns_artifacts(mock_agent_llm: MagicMock) -> None:
    """P5-022: specialist agents return structured AgentResult."""
    agent = CodingAgent(agent_llm=mock_agent_llm)
    result = agent.execute("Créer une fonction Python")

    assert isinstance(result, AgentResult)
    assert result.artifacts


def test_agent_manager_unknown_agent_returns_zero_confidence() -> None:
    """P5-023: missing agent degrades gracefully."""
    manager = AgentManager()
    result = manager.execute("nonexistent", "task")

    assert result.confidence == 0.0
    assert "introuvable" in result.summary.lower()

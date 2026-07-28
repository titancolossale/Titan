# =====================================
# Titan Single Agent Path Tests
# =====================================

"""Regression guards for P0: one orchestration path per user turn."""

from __future__ import annotations

from agents.agent_result import AgentResult
from unittest.mock import MagicMock

from brain.brain import Brain
from config.settings import TITAN_MAX_AGENT_HANDOFFS


def test_brain_think_executes_agents_once_per_task_list(brain: Brain) -> None:
    """P1-072: orchestrator must call execute once per task, not doubled.

    Agent handoffs are capped by TITAN_MAX_AGENT_HANDOFFS (complex-path limit).
    """
    message = "test code python"
    expected_tasks = brain.task_manager.create_tasks(message)
    expected_count = min(len(expected_tasks), TITAN_MAX_AGENT_HANDOFFS)
    assert expected_count >= 1
    assert len(expected_tasks) >= 1

    mock_execute = MagicMock(
        return_value=AgentResult(
            agent_name="coding",
            task="mock",
            summary="mock agent result",
        ),
    )
    brain.agent_manager.execute = mock_execute

    brain.think(message)

    assert mock_execute.call_count == expected_count

# =====================================
# Titan Orchestrator Error Handling Tests
# =====================================

"""Tests for graceful agent failures inside TaskOrchestrator (P1-112)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain.brain import Brain


def test_think_returns_llm_response_when_agent_raises(brain: Brain) -> None:
    """P1-112: agent execute failure must not crash think(); LLM still responds."""
    brain.agent_manager.execute = MagicMock(
        side_effect=RuntimeError("simulated agent failure")
    )

    result = brain.think("test code python")

    assert result == "Réponse de test."
    brain.llm.ask.assert_called_once()


def test_orchestrator_agent_failure_is_logged(
    brain: Brain,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """P1-112: agent failure must be logged at ERROR with stack trace."""
    brain.agent_manager.execute = MagicMock(
        side_effect=RuntimeError("simulated agent failure")
    )

    with caplog.at_level("ERROR", logger="core.task_orchestrator"):
        brain.think("test code python")

    assert any(
        "Agent" in record.message and "failed during orchestration" in record.message
        for record in caplog.records
    )
    assert any(record.exc_info is not None for record in caplog.records)

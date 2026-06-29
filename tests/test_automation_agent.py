# =====================================
# Titan Automation Agent Tests
# =====================================

"""Tests for Phase 9 automation agent (P9-082)."""

from __future__ import annotations

from agents.agent_context import AgentContext
from agents.automation_agent import AutomationAgent
from brain.autonomy_policy import AutonomyPolicy


def test_automation_plans_confirmation_gated_steps() -> None:
    """Write/exec steps require confirmation under default policy."""
    agent = AutomationAgent(AutonomyPolicy(require_confirmation_writes=True))
    result = agent.execute(
        "automatise l'écriture d'un fichier python",
        AgentContext(user_message="automatise l'écriture d'un fichier python", task="automatise"),
    )

    assert "confirmation requise" in result.result
    assert any("file_write" in artifact for artifact in result.artifacts)


def test_automation_no_confirmation_when_policy_disabled() -> None:
    """When confirmations disabled, steps may run automatically."""
    policy = AutonomyPolicy(
        require_confirmation_writes=False,
        require_confirmation_exec=False,
    )
    agent = AutomationAgent(policy)
    steps = agent.plan_workflow("écrire un fichier test", AgentContext(user_message="", task=""))

    assert all(not step.requires_confirmation for step in steps)

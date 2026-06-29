# =====================================
# Titan AgentSelector Tests
# =====================================

"""Baseline smoke tests for AgentSelector keyword routing."""

from __future__ import annotations

import pytest

from agents.agent_selector import AgentSelector


@pytest.fixture
def selector() -> AgentSelector:
    """Fresh AgentSelector instance for each test."""
    return AgentSelector()


@pytest.mark.parametrize(
    ("message", "expected_agent"),
    [
        ("Aide-moi à coder un script Python", "coding"),
        ("Cherche des informations sur google", "research"),
        ("Organise mon planning de la semaine", "planning"),
        ("Explique la logique derrière cette erreur", "reasoning"),
        ("Bonjour Titan, comment vas-tu ?", "base"),
    ],
)
def test_select_agent_routes_by_keyword(
    selector: AgentSelector,
    message: str,
    expected_agent: str,
) -> None:
    """User messages must route to the documented specialist or base fallback."""
    assert selector.select_agent(message) == expected_agent

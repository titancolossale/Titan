# =====================================
# Titan Agent Registry Tests
# =====================================

"""Tests for unified agent routing registry (Phase 5 — P5-010–P5-012)."""

from __future__ import annotations

import pytest

from agents.agent_registry import AgentRegistry, default_registry
from agents.agent_selector import AgentSelector
from core.task_manager import TaskManager


@pytest.fixture
def registry() -> AgentRegistry:
    return AgentRegistry()


@pytest.fixture
def selector(registry: AgentRegistry) -> AgentSelector:
    return AgentSelector(registry=registry)


@pytest.fixture
def task_manager(registry: AgentRegistry) -> TaskManager:
    return TaskManager(agent_manager=None, registry=registry)


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
    """P5-011: selector routes match legacy keyword behavior."""
    assert selector.select_agent(message) == expected_agent


def test_coding_route_creates_three_agent_pipeline(task_manager: TaskManager) -> None:
    """P5-012: coding keywords produce planning → coding → reasoning tasks."""
    tasks = task_manager.create_tasks("test code python")
    agent_names = [name for name, _ in tasks]

    assert agent_names == ["planning", "coding", "reasoning"]
    assert all("test code python" in task for _, task in tasks)


def test_research_route_creates_two_agent_pipeline(task_manager: TaskManager) -> None:
    """P5-012: research keywords produce research → reasoning tasks."""
    tasks = task_manager.create_tasks("recherche sur internet")
    agent_names = [name for name, _ in tasks]

    assert agent_names == ["research", "reasoning"]


def test_default_route_when_no_keywords_match(task_manager: TaskManager) -> None:
    """P5-012: unmatched messages fall back to reasoning → planning."""
    tasks = task_manager.create_tasks("Bonjour Titan")
    agent_names = [name for name, _ in tasks]

    assert agent_names == ["reasoning", "planning"]


def test_selector_primary_agent_in_pipeline(registry: AgentRegistry) -> None:
    """P5-010: auto-select primary agent appears in orchestration pipeline."""
    for route in registry.routes:
        message = f"test {route.keywords[0]} message"
        primary = registry.select_agent(message)
        pipeline_agents = [name for name, _ in registry.create_tasks(message)]

        assert primary == route.primary_agent
        assert primary in pipeline_agents


def test_coding_beats_planning_when_both_match(registry: AgentRegistry) -> None:
    """P5-010: higher-priority coding route wins over planning keywords."""
    message = "code un script pour organiser mon planning"
    route = registry.match_route(message)

    assert route is not None
    assert route.name == "coding"
    assert registry.select_agent(message) == "coding"


def test_default_registry_is_singleton() -> None:
    """P5-010: module default registry is shared and importable."""
    assert default_registry.select_agent("python code") == "coding"

# =====================================
# Titan Agent Selector
# =====================================

"""Single-agent keyword routing via unified registry (Phase 5 — P5-011)."""

from __future__ import annotations

from agents.agent_registry import AgentRegistry, default_registry


class AgentSelector:
    """Selects one specialist agent from user message keywords."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or default_registry

    def select_agent(self, message: str) -> str:
        return self._registry.select_agent(message)

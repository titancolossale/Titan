# =====================================
# Titan Base Agent
# =====================================

"""Abstract agent contract with structured results (Phase 5 — P5-022)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agents.agent_context import AgentContext
from agents.agent_result import AgentResult


class BaseAgent(ABC):
    """Internal specialist worker — output is consumed by Brain, not shown as Titan voice."""

    def __init__(self, name: str, agent_key: str = "base") -> None:
        self.name = name
        self.agent_key = agent_key

    def execute(
        self,
        task: str,
        context: AgentContext | None = None,
    ) -> AgentResult | str:
        """Run the agent task; subclasses implement structured execution."""
        ctx = context or AgentContext(user_message=task, task=task)
        return self._execute(task, ctx)

    @abstractmethod
    def _execute(self, task: str, context: AgentContext) -> AgentResult:
        """Subclass hook — must return structured AgentResult."""

    @staticmethod
    def coerce_result(
        agent_name: str,
        task: str,
        output: AgentResult | str,
    ) -> AgentResult:
        """Normalize legacy string returns to AgentResult."""
        if isinstance(output, AgentResult):
            return output
        return AgentResult.from_text(agent_name, task, output)

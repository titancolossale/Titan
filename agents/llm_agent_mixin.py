# =====================================
# Titan LLM-Backed Agent Mixin
# =====================================

"""Shared LLM execution helper for specialist agents (Phase 5 — P5-041)."""

from __future__ import annotations

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.agent_response_parser import parse_agent_output
from agents.agent_result import AgentResult


class LLMAgentMixin:
    """Mixin providing scoped LLM execution for specialist agents."""

    agent_key: str = "base"
    _agent_llm: AgentLLM | None = None

    def run_llm(self, task: str, context: AgentContext) -> AgentResult:
        """Call scoped AgentLLM and parse structured output."""
        llm = self._agent_llm or AgentLLM()
        raw = llm.ask(self.agent_key, task, context)
        return parse_agent_output(self.agent_key, task, raw)

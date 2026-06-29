# =====================================
# Titan Web Agent
# =====================================

"""Web research agent via search provider abstraction (Phase 9 — P9-081)."""

from __future__ import annotations

from agents.agent_context import AgentContext
from agents.agent_result import AgentResult
from agents.base_agent import BaseAgent
from tools.web_search_provider import StubWebSearchProvider, WebSearchProvider


class WebAgent(BaseAgent):
    """Internal web research specialist — uses provider interface, not raw APIs."""

    def __init__(self, provider: WebSearchProvider | None = None) -> None:
        super().__init__("Titan Web Agent", agent_key="web")
        self._provider = provider or StubWebSearchProvider()

    def _execute(self, task: str, context: AgentContext) -> AgentResult:
        query = self._extract_query(task, context)
        response = self._provider.search(query)

        body = response.format_for_agent()
        if context.prompt_block():
            body = f"{context.prompt_block()}\n\n{body}"

        confidence = 0.7 if response.results else 0.4
        summary = (
            f"Recherche web ({response.provider}) : "
            f"{len(response.results)} résultat(s) pour « {query} »."
        )

        return AgentResult(
            agent_name=self.agent_key,
            task=task,
            summary=summary,
            artifacts=[body] if body else [],
            confidence=confidence,
        )

    @staticmethod
    def _extract_query(task: str, context: AgentContext) -> str:
        """Derive search query from task or user message."""
        for candidate in (task, context.user_message):
            cleaned = candidate.strip()
            if cleaned:
                return cleaned[:200]
        return "recherche"

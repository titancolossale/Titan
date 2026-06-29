# =====================================
# Titan Memory Agent
# =====================================

"""Memory Agent v1 — summarizes session notes into long-term storage (P5-050)."""

from __future__ import annotations

import re

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.agent_result import AgentResult
from agents.base_agent import BaseAgent
from agents.agent_response_parser import parse_agent_output
from memory.memory_service import MemoryService

_CATEGORY_LINE_RE = re.compile(
    r"\[(goals|preferences|projects|notes)\]\s*(.+)",
    re.IGNORECASE,
)


class MemoryAgent(BaseAgent):
    """Summarizes session notes and writes categorized long-term memory."""

    def __init__(
        self,
        memory_service: MemoryService,
        agent_llm: AgentLLM | None = None,
    ) -> None:
        super().__init__("Titan Memory Agent", agent_key="memory")
        self._memory_service = memory_service
        self._agent_llm = agent_llm

    def _execute(self, task: str, context: AgentContext) -> AgentResult:
        notes = self._memory_service.get_session_notes()
        if not notes:
            return AgentResult(
                agent_name=self.agent_key,
                task=task,
                summary="Aucune note de session à résumer.",
                confidence=1.0,
            )

        enriched = AgentContext(
            user_message=context.user_message,
            task=f"{task}\n\nNotes de session :\n" + "\n".join(f"- {n}" for n in notes),
            current_user=context.current_user,
            situational_context=context.situational_context,
            retrieved_memory=context.retrieved_memory,
            state=context.state,
            mission=context.mission,
            executive_analysis=context.executive_analysis,
            active_project=context.active_project,
            current_phase=context.current_phase,
            current_goal=context.current_goal,
        )

        llm = self._agent_llm or AgentLLM()
        raw = llm.ask(self.agent_key, enriched.task, enriched)
        saved = self._persist_candidates(context.current_user, raw)
        result = parse_agent_output(self.agent_key, enriched.task, raw)
        if saved:
            result = AgentResult(
                agent_name=result.agent_name,
                task=result.task,
                summary=f"{result.summary}\n\n{saved} note(s) persistée(s) en mémoire long terme.",
                artifacts=result.artifacts,
                confidence=result.confidence,
                tools_used=result.tools_used,
            )
        return result

    def _persist_candidates(self, user: str, text: str) -> int:
        """Parse [category] lines from raw LLM output and write to long-term memory."""
        saved = 0
        seen: set[str] = set()
        for match in _CATEGORY_LINE_RE.finditer(text):
                category = match.group(1).lower()
                content = match.group(2).strip()
                key = f"{category}:{content}"
                if not content or key in seen:
                    continue
                seen.add(key)
                self._memory_service.store_categorized(user, category, content)
                saved += 1
        return saved

# =====================================
# Titan Agent LLM
# =====================================

"""Scoped LLM calls for specialist agents — no full constitution duplicate (P5-030)."""

from __future__ import annotations

import logging
from pathlib import Path

from agents.agent_context import AgentContext
from brain.llm import LLM, load_prompt_file
from brain.llm_provider import LLMProvider
from config.settings import PROMPTS_DIR

logger = logging.getLogger(__name__)

_AGENT_PROMPT_MAP: dict[str, str] = {
    "coding": "agents/coding.md",
    "research": "agents/research.md",
    "planning": "agents/planning.md",
    "reasoning": "agents/reasoning.md",
    "base": "agents/base.md",
    "memory": "agents/memory.md",
}

_FALLBACK_INSTRUCTIONS = (
    "Tu es un agent interne de Titan. Produis un artefact interne concis en français. "
    "Ne parle pas directement à l'utilisateur."
)


class AgentLLM:
    """Controlled LLM gateway for agent-scoped prompts."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        self._llm = llm if llm is not None else LLM()
        self._prompts_dir = prompts_dir if prompts_dir is not None else PROMPTS_DIR

    def load_instructions(self, agent_key: str) -> str:
        """Load scoped system instructions for an agent type."""
        relative = _AGENT_PROMPT_MAP.get(agent_key, _AGENT_PROMPT_MAP["base"])
        instructions = load_prompt_file(relative, self._prompts_dir)
        if not instructions:
            logger.warning("Agent prompt missing for %s — using fallback", agent_key)
            return _FALLBACK_INSTRUCTIONS
        return instructions

    def build_prompt(self, task: str, context: AgentContext) -> str:
        """Assemble the user prompt for an agent LLM call."""
        blocks = [
            context.prompt_block(),
            f"--- TÂCHE ASSIGNÉE ---\n{task.strip()}",
            f"--- DEMANDE UTILISATEUR ORIGINALE ---\n{context.user_message.strip()}",
        ]
        return "\n\n".join(block for block in blocks if block.strip())

    def ask(self, agent_key: str, task: str, context: AgentContext) -> str:
        """Call LLM with agent-scoped instructions only."""
        instructions = self.load_instructions(agent_key)
        prompt = self.build_prompt(task, context)

        if isinstance(self._llm, LLM):
            return self._llm.ask_scoped(prompt, instructions)

        # Test doubles and future providers: prepend instructions to prompt.
        scoped_prompt = f"{instructions}\n\n---\n\n{prompt}"
        return self._llm.ask(scoped_prompt)

# =====================================
# Titan Prompt Builder
# =====================================

"""Assembles labeled LLM prompt sections with truncation policy (Phase 2 — P2-011)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from brain.pipeline.context_bundle import ThinkContext
from config.settings import MAX_PROMPT_TOKENS

# Rough chars-per-token estimate for truncation (no tiktoken dependency yet).
_CHARS_PER_TOKEN = 4


@dataclass
class PromptBuilder:
    """Builds the user-facing LLM prompt from a ``ThinkContext``."""

    max_chars: int = MAX_PROMPT_TOKENS * _CHARS_PER_TOKEN

    def build(self, ctx: ThinkContext) -> str:
        """Assemble all prompt sections; apply truncation if over budget."""
        sections = self._ordered_sections(ctx)
        prompt = self._join_sections(sections)
        if len(prompt) <= self.max_chars:
            return prompt
        return self._truncate(sections)

    def _ordered_sections(self, ctx: ThinkContext) -> list[tuple[str, str]]:
        """Return labeled sections in canonical prompt order."""
        sections: list[tuple[str, str]] = [
            ("CONTEXTE ACTUEL", ctx.situational_context or "Aucun contexte disponible."),
            ("MÉMOIRE PERMANENTE", ctx.retrieved_memory or "Aucune mémoire pertinente trouvée."),
            ("ÉTAT ACTUEL", self._format_json(ctx.state)),
            ("MISSION ACTIVE", self._format_json(ctx.mission)),
            ("EXECUTIVE ANALYSIS", ctx.executive_analysis or "Aucune analyse exécutive."),
        ]
        if ctx.structured_plan_text:
            sections.append(("PLAN D'ACTION", ctx.structured_plan_text))
        if ctx.initiative_text:
            sections.append(("INITIATIVE", ctx.initiative_text))
        if ctx.learning_text:
            sections.append(("APPRENTISSAGE", ctx.learning_text))
        if ctx.knowledge_hits:
            sections.append(("CONNAISSANCES", ctx.knowledge_hits))
        if ctx.tool_status_text:
            sections.append(("SANTÉ OUTILS ET PROVIDERS", ctx.tool_status_text))
        if ctx.conversation_window:
            sections.append(
                ("CONVERSATION RÉCENTE", "\n".join(ctx.conversation_window)),
            )
        if ctx.agent_results_text:
            sections.append(("RÉSULTATS DES AGENTS", ctx.agent_results_text))
        if ctx.tool_results_text:
            sections.append(("RÉSULTATS OUTILS", ctx.tool_results_text))
        sections.append(("QUESTION DE L'UTILISATEUR", ctx.user_message))
        return sections

    @staticmethod
    def _format_json(data: dict) -> str:
        """Format state/mission as readable JSON text, not raw dict repr."""
        if not data:
            return "{}"
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def _join_sections(sections: list[tuple[str, str]]) -> str:
        blocks: list[str] = []
        for label, body in sections:
            blocks.append(
                f"=========================================\n{label}\n"
                f"=========================================\n\n{body.strip()}\n"
            )
        return "\n".join(blocks)

    def _truncate(self, sections: list[tuple[str, str]]) -> str:
        """Truncate lower-priority sections; user message is never truncated."""
        priority_labels = [
            "QUESTION DE L'UTILISATEUR",
            "MISSION ACTIVE",
            "MÉMOIRE PERMANENTE",
            "CONTEXTE ACTUEL",
            "RÉSULTATS DES AGENTS",
            "RÉSULTATS OUTILS",
            "SANTÉ OUTILS ET PROVIDERS",
            "EXECUTIVE ANALYSIS",
            "PLAN D'ACTION",
            "INITIATIVE",
            "APPRENTISSAGE",
            "ÉTAT ACTUEL",
            "CONVERSATION RÉCENTE",
            "CONNAISSANCES",
        ]
        label_to_section = {label: (label, body) for label, body in sections}
        ordered = [label_to_section[label] for label in priority_labels if label in label_to_section]

        # Drop lowest-priority sections until within budget.
        while len(ordered) > 1:
            prompt = self._join_sections(ordered)
            if len(prompt) <= self.max_chars:
                return prompt
            ordered.pop()

        prompt = self._join_sections(ordered)
        if len(prompt) <= self.max_chars:
            return prompt

        # Last resort: truncate the user message body (keep label).
        label, body = ordered[0]
        overflow = len(prompt) - self.max_chars
        trimmed_body = body[: max(0, len(body) - overflow - 20)] + "\n[... tronqué ...]"
        return self._join_sections([(label, trimmed_body)])

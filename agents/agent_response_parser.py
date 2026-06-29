# =====================================
# Titan Agent Response Parser
# =====================================

"""Parse scoped LLM output into structured AgentResult (Phase 5 — P5-040)."""

from __future__ import annotations

import re

from agents.agent_result import AgentResult

_CODE_BLOCK_RE = re.compile(r"```[\w]*\n(.*?)```", re.DOTALL)
_NUMBERED_LINE_RE = re.compile(r"^\s*\d+[\.\)]\s+(.+)$", re.MULTILINE)


def parse_agent_output(agent_key: str, task: str, raw: str) -> AgentResult:
    """Convert agent LLM text into summary + artifacts."""
    text = raw.strip()
    if not text:
        return AgentResult(
            agent_name=agent_key,
            task=task,
            summary="Aucune sortie de l'agent.",
            confidence=0.0,
        )

    code_blocks = [block.strip() for block in _CODE_BLOCK_RE.findall(text) if block.strip()]
    numbered_items = [
        match.group(1).strip()
        for match in _NUMBERED_LINE_RE.finditer(text)
        if match.group(1).strip()
    ]

    summary = _extract_summary(text)
    artifacts = code_blocks or numbered_items

    return AgentResult(
        agent_name=agent_key,
        task=task,
        summary=summary,
        artifacts=artifacts,
    )


def _extract_summary(text: str) -> str:
    """Prefer explicit Résumé section; otherwise use first non-empty paragraph."""
    lower = text.lower()
    for marker in ("**résumé**", "résumé :", "résumé:", "## résumé"):
        index = lower.find(marker)
        if index >= 0:
            remainder = text[index + len(marker):].strip()
            paragraph = remainder.split("\n\n", 1)[0].strip()
            if paragraph:
                return paragraph

    for paragraph in text.split("\n\n"):
        cleaned = paragraph.strip()
        if cleaned and not cleaned.startswith("```"):
            return cleaned

    return text[:500]

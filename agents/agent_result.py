# =====================================
# Titan Agent Result
# =====================================

"""Structured agent execution output (Phase 5 — P5-020)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResult:
    """Structured output from a specialist agent execution."""

    agent_name: str
    task: str
    summary: str
    artifacts: list[str] = field(default_factory=list)
    confidence: float = 1.0
    tools_used: list[str] = field(default_factory=list)

    @property
    def result(self) -> str:
        """Prompt-ready text for orchestrator and PromptBuilder (backward compat)."""
        lines = [
            f"Résumé : {self.summary.strip()}",
        ]
        if self.artifacts:
            lines.append("")
            lines.append("Artefacts :")
            lines.extend(f"- {artifact.strip()}" for artifact in self.artifacts)
        if self.tools_used:
            lines.append("")
            lines.append(f"Outils utilisés : {', '.join(self.tools_used)}")
        if self.confidence < 1.0:
            lines.append("")
            lines.append(f"Confiance : {self.confidence:.0%}")
        return "\n".join(lines)

    @classmethod
    def from_text(
        cls,
        agent_name: str,
        task: str,
        text: str,
        *,
        confidence: float = 1.0,
    ) -> AgentResult:
        """Wrap legacy string output as a structured result."""
        return cls(
            agent_name=agent_name,
            task=task,
            summary=text.strip(),
            confidence=confidence,
        )

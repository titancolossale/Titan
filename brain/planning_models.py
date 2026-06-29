# =====================================
# Titan Planning Models
# =====================================

"""Structured plan types for mission-linked planning (Phase 8 — P8-030)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """One actionable step within a structured plan."""

    order: int
    description: str
    linked_mission_step: str | None = None
    action_type: str = "respond"
    rationale: str = ""


@dataclass
class StructuredPlan:
    """Mission-aware execution plan produced by PlanningEngine."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_focus: str = ""
    mission_step: str | None = None
    domain: str = "general"

    def format_for_prompt(self) -> str:
        """French formatted block for PromptBuilder injection."""
        lines = [f"Objectif : {self.goal}"]
        if self.mission_step:
            lines.append(f"Étape mission liée : {self.mission_step}")
        if self.current_focus:
            lines.append(f"Focus actuel : {self.current_focus}")
        if self.domain != "general":
            lines.append(f"Domaine : {self.domain}")
        if self.steps:
            lines.append("Plan d'action :")
            for step in self.steps:
                marker = "→" if step.description == self.current_focus else f"{step.order}."
                suffix = f" [{step.action_type}]" if step.action_type != "respond" else ""
                lines.append(f"  {marker} {step.description}{suffix}")
        return "\n".join(lines)

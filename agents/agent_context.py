# =====================================
# Titan Agent Context
# =====================================

"""Context bundle injected into agent execution (Phase 5 — P5-021)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.pipeline.context_bundle import ThinkContext
    from context.models import ContextSnapshot


@dataclass
class AgentContext:
    """Operational context available to specialist agents during execute()."""

    user_message: str
    task: str
    current_user: str = "Nolan"
    situational_context: str = ""
    retrieved_memory: str = ""
    state: dict = field(default_factory=dict)
    mission: dict = field(default_factory=dict)
    # Phase 14.3 — shared WorkspaceState-derived mission awareness.
    mission_context: dict = field(default_factory=dict)
    executive_analysis: str = ""
    active_project: str = ""
    current_phase: str = ""
    current_goal: str = ""

    @classmethod
    def from_think_context(cls, think_ctx: ThinkContext, task: str) -> AgentContext:
        """Build agent context from the Brain pipeline bundle."""
        snapshot = think_ctx.context_snapshot
        mission_context = think_ctx.mission_context
        mission_context_dict: dict = {}
        if mission_context is not None:
            mission_context_dict = {
                "active_mission": mission_context.active_mission,
                "status": mission_context.status,
                "progress": mission_context.progress,
                "priority": mission_context.priority,
                "stage": mission_context.stage,
                "last_completed_step": mission_context.last_completed_step,
                "last_summary": mission_context.last_summary,
                "progress_updated_at": mission_context.progress_updated_at,
                "current_objective": mission_context.current_objective,
                "queue_count": mission_context.queue_count,
                "paused_count": mission_context.paused_count,
            }
        return cls(
            user_message=think_ctx.user_message,
            task=task,
            current_user=think_ctx.current_user,
            situational_context=think_ctx.situational_context,
            retrieved_memory=think_ctx.retrieved_memory,
            state=dict(think_ctx.state),
            mission=dict(think_ctx.mission),
            mission_context=mission_context_dict,
            executive_analysis=think_ctx.executive_analysis,
            active_project=_snapshot_field(snapshot, "active_project"),
            current_phase=_snapshot_field(snapshot, "current_phase"),
            current_goal=_snapshot_field(snapshot, "current_goal"),
        )

    def prompt_block(self) -> str:
        """Format context for agent LLM prompts."""
        sections = [
            ("UTILISATEUR", self.current_user),
            ("PROJET ACTIF", self.active_project or "Non spécifié"),
            ("PHASE", self.current_phase or "Non spécifiée"),
            ("OBJECTIF", self.current_goal or "Non spécifié"),
        ]
        if self.situational_context:
            sections.append(("CONTEXTE", self.situational_context))
        if self.retrieved_memory:
            sections.append(("MÉMOIRE PERTINENTE", self.retrieved_memory))
        if self.executive_analysis:
            sections.append(("ANALYSE EXÉCUTIVE", self.executive_analysis))

        blocks: list[str] = []
        for label, body in sections:
            blocks.append(f"--- {label} ---\n{body.strip()}")
        return "\n\n".join(blocks)


def _snapshot_field(snapshot: ContextSnapshot | None, field_name: str) -> str:
    if snapshot is None:
        return ""
    return str(getattr(snapshot, field_name, "") or "")

# =====================================
# Titan Prompt Builder
# =====================================

"""Assembles labeled LLM prompt sections with truncation policy (Phase 2 — P2-011)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from brain.pipeline.context_bundle import ThinkContext
from config.settings import MAX_PROMPT_TOKENS

# Rough chars-per-token estimate for truncation (no tiktoken dependency yet).
_CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)


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
        """Return labeled sections in canonical prompt order.

        Conversation intelligence layers (Phase 12.2) appear before the user
        message: recent → summary → pinned facts → resolved reference.
        System instructions remain on the LLM system prompt (not duplicated here).

        Phase 14.3 — concise Current Mission block is attached only when
        ``ctx.mission_context`` reports an active mission.
        Phase 14.4 — Mission Resume block is attached with the same gate.
        Phase 14.5 — Active Mission + queue/paused counts (concise metadata only).
        Phase 15.1 — Current Project / Project Progress when project_context active.
        Phase 15.2 — Current Mission / Last Completed Step / Current Objective
        attached in the same project block when an active project exists.
        Phase 16.1 — Current Goal when goal_context active.
        Phase 16.2 — Goal Progress / Current Project / Current Mission in goal block.
        Phase 16.3 — Confidence / Reason for selection in goal block.
        Phase 17.1 — Current Plan / Next Actions / Priority / Blocked Reason.
        Phase 17.2 — Plan Revision / Latest Changes.
        Phase 17.3 — Current Decision / Reason / Confidence / Top Candidate Actions.
        Phase 18.1 — Current Execution / Running Task / Execution Status.
        """
        sections: list[tuple[str, str]] = [
            ("CONTEXTE ACTUEL", ctx.situational_context or "Aucun contexte disponible."),
            ("MÉMOIRE PERMANENTE", ctx.retrieved_memory or "Aucune mémoire pertinente trouvée."),
            ("ÉTAT ACTUEL", self._format_json(ctx.state)),
            ("MISSION ACTIVE", self._format_json(ctx.mission)),
        ]
        goal_context = getattr(ctx, "goal_context", None)
        if goal_context is not None and goal_context.has_active_goal:
            sections.append(("CONTEXTE GOAL", goal_context.to_prompt_block()))
            logger.info(
                "GOAL_PROMPT_ATTACHED name=%s progress=%s confidence=%s reason=%s "
                "project=%s mission=%s",
                goal_context.name,
                goal_context.progress,
                getattr(goal_context, "match_confidence", None),
                getattr(goal_context, "selection_reason", None),
                getattr(goal_context, "current_project", None),
                getattr(goal_context, "current_mission", None),
            )
        project_context = getattr(ctx, "project_context", None)
        if project_context is not None and project_context.has_active_project:
            sections.append(("CONTEXTE PROJET", project_context.to_prompt_block()))
            logger.info(
                "PROJECT_PROMPT_ATTACHED name=%s status=%s progress=%s "
                "active_mission=%s last_completed=%s objective=%s",
                project_context.name,
                project_context.status,
                project_context.progress,
                getattr(project_context, "active_mission", None),
                getattr(project_context, "last_completed_step", None),
                getattr(project_context, "current_objective", None),
            )
        mission_context = ctx.mission_context
        if mission_context is not None and mission_context.has_active_mission:
            sections.append(("CONTEXTE MISSION", mission_context.to_prompt_block()))
            sections.append(("MISSION RESUME", mission_context.to_resume_prompt_block()))
            logger.info(
                "MISSION_PROMPT_ATTACHED title=%s status=%s queue=%s paused=%s",
                mission_context.active_mission,
                mission_context.status,
                mission_context.queue_count,
                mission_context.paused_count,
            )
        sections.append(
            ("EXECUTIVE ANALYSIS", ctx.executive_analysis or "Aucune analyse exécutive."),
        )
        if ctx.structured_plan_text:
            sections.append(("PLAN D'ACTION", ctx.structured_plan_text))
            execution_plan = getattr(ctx, "execution_plan", None)
            logger.info(
                "PLAN_PROMPT_ATTACHED goal=%s project=%s mission=%s "
                "priority=%s blocked=%s actions=%s revision=%s reason=%s",
                getattr(execution_plan, "current_goal", None),
                getattr(execution_plan, "current_project", None),
                getattr(execution_plan, "current_mission", None),
                getattr(execution_plan, "priority_score", None),
                getattr(execution_plan, "blocked_reason", None),
                len(getattr(execution_plan, "next_actions", None) or []),
                getattr(execution_plan, "revision", None),
                getattr(execution_plan, "change_reason", None),
            )
        decision_text = getattr(ctx, "decision_text", "") or ""
        if decision_text:
            sections.append(("DÉCISION ACTUELLE", decision_text))
            execution_decision = getattr(ctx, "execution_decision", None)
            logger.info(
                "DECISION_PROMPT_ATTACHED action=%s confidence=%s priority=%s "
                "risk=%s expected_value=%s success_rate=%s learning_confidence=%s",
                getattr(execution_decision, "selected_action", None),
                getattr(execution_decision, "confidence", None),
                getattr(execution_decision, "priority", None),
                getattr(execution_decision, "risk_score", None),
                getattr(execution_decision, "expected_value", None),
                getattr(execution_decision, "success_rate", None),
                getattr(execution_decision, "learning_confidence", None),
            )
        execution_text = getattr(ctx, "execution_text", "") or ""
        if execution_text:
            sections.append(("EXÉCUTION ACTUELLE", execution_text))
            execution_task = getattr(ctx, "execution_task", None)
            safety = getattr(execution_task, "safety", None)
            logger.info(
                "EXECUTION_PROMPT_ATTACHED action=%s status=%s task_id=%s "
                "decision_id=%s risk_level=%s confirmation_required=%s",
                getattr(execution_task, "action", None),
                getattr(getattr(execution_task, "status", None), "value", None)
                or getattr(execution_task, "status", None),
                getattr(execution_task, "task_id", None),
                getattr(execution_task, "decision_id", None),
                getattr(execution_task, "risk_level", None)
                or getattr(safety, "risk_level", None),
                getattr(safety, "requires_confirmation", None),
            )
        if ctx.initiative_text:
            sections.append(("INITIATIVE", ctx.initiative_text))
        if ctx.learning_text:
            sections.append(("APPRENTISSAGE", ctx.learning_text))
        if ctx.knowledge_hits:
            sections.append(("CONNAISSANCES", ctx.knowledge_hits))
        if ctx.tool_status_text:
            sections.append(("SANTÉ OUTILS ET PROVIDERS", ctx.tool_status_text))
        # Layered conversation continuity (Phase 12.2)
        if ctx.conversation_window:
            sections.append(
                ("CONVERSATION RÉCENTE", "\n".join(ctx.conversation_window)),
            )
        if ctx.conversation_summary:
            sections.append(("RÉSUMÉ CONVERSATION", ctx.conversation_summary))
        if ctx.pinned_facts_text:
            sections.append(("FAITS ÉPINGLÉS", ctx.pinned_facts_text))
        if ctx.reference_resolution:
            sections.append(("RÉFÉRENCE RÉSOLUE", ctx.reference_resolution))
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
            "CONTEXTE GOAL",
            "CONTEXTE PROJET",
            "CONTEXTE MISSION",
            "MISSION RESUME",
            "MÉMOIRE PERMANENTE",
            "CONTEXTE ACTUEL",
            "FAITS ÉPINGLÉS",
            "RÉFÉRENCE RÉSOLUE",
            "RÉSUMÉ CONVERSATION",
            "RÉSULTATS DES AGENTS",
            "RÉSULTATS OUTILS",
            "SANTÉ OUTILS ET PROVIDERS",
            "EXECUTIVE ANALYSIS",
            "PLAN D'ACTION",
            "DÉCISION ACTUELLE",
            "EXÉCUTION ACTUELLE",
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

# =====================================
# Titan Planning Engine
# =====================================

"""Structured planning for Brain pipeline.

Phase 8 — turn-scoped ``StructuredPlan`` linked to mission steps (P8-031).
Phase 17.1 — next-action ``Plan`` from WorkspaceState + Goal / Project / Mission
(\"What should I do next?\"). Reuses GoalManager / ProjectManager / MissionManager
entities; does not recreate them.

Phase 17.2 — dynamic plan evolution: incremental updates when mission /
project / goal / workspace change. Diagnostics: PLAN_UPDATED, PLAN_REBUILT,
PLAN_REFRESHED, PLAN_REVISION.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from brain.planner import (
    EVOLVE_CREATED,
    EVOLVE_REBUILT,
    EVOLVE_REFRESHED,
    EVOLVE_UPDATED,
    Planner,
)
from brain.planning_models import (
    CHANGE_REASON_CREATED,
    CHANGE_REASON_MISSION_COMPLETED,
    Plan,
    PlanStatus,
    PlanStep,
    StructuredPlan,
)

logger = logging.getLogger(__name__)

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trading": ("trading", "backtest", "nq", "robot", "marché", "position"),
    "coding": ("code", "python", "fonction", "fichier", "script", "module"),
    "research": ("recherche", "analyser", "information", "étude", "etude"),
    "planning": ("plan", "organiser", "étapes", "roadmap", "projet"),
}


class PlanningEngine:
    """Produce next-action plans and Phase 8 turn-scoped structured plans."""

    def __init__(self, planner: Planner | None = None) -> None:
        self._planner = planner or Planner()
        self._active_plan: Plan | None = None

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def active_plan(self) -> Plan | None:
        return self._active_plan

    def plan_next(
        self,
        *,
        workspace: Any | None = None,
        goal: Any | None = None,
        project: Any | None = None,
        mission: Any | None = None,
        mission_lookup: Callable[[str], Any | None] | None = None,
        now: datetime | None = None,
        change_reason: str | None = None,
    ) -> Plan:
        """Build or evolve the next execution plan from workspace hierarchy.

        Single planning pass — callers must not invoke this twice per think
        unless a mid-turn trigger fires (mission completed / blocked).
        Does not call ``StateManager.load()``; expects a request-scoped workspace.

        Phase 17.2 — compares the active plan to the new workspace and only
        recomputes what changed (incremental update / rebuild / refresh).
        """
        stamp = now or datetime.now(timezone.utc)
        previous = self._active_plan

        if previous is None:
            plan = self._planner.build(
                workspace=workspace,
                goal=goal,
                project=project,
                mission=mission,
                mission_lookup=mission_lookup,
                now=stamp,
                change_reason=change_reason or CHANGE_REASON_CREATED,
                revision=1,
                latest_changes=[change_reason or CHANGE_REASON_CREATED],
            )
            self._active_plan = plan
            self._emit_evolution(plan, EVOLVE_CREATED)
            self._emit_status_diagnostics(plan)
            return plan

        plan, mode = self._planner.evolve(
            previous,
            workspace=workspace,
            goal=goal,
            project=project,
            mission=mission,
            mission_lookup=mission_lookup,
            now=stamp,
            forced_reason=change_reason,
        )
        self._active_plan = plan
        self._emit_evolution(plan, mode)
        self._emit_status_diagnostics(plan)
        return plan

    def complete_plan(self, plan: Plan | None = None) -> Plan:
        """Mark the active (or given) plan completed and evolve revision.

        Phase 17.2 — increments revision with ``mission_completed`` reason.
        """
        target = plan or self._active_plan
        if target is None:
            target = Plan.empty()
        stamp = datetime.now(timezone.utc)
        revision = target.revision + 1 if target.status != PlanStatus.COMPLETED else target.revision
        completed = Plan(
            current_goal=target.current_goal,
            current_project=target.current_project,
            current_mission=target.current_mission,
            next_actions=[],
            priority_score=target.priority_score,
            estimated_duration=0.0,
            dependencies=list(target.dependencies),
            blocked_reason=None,
            created_at=target.created_at,
            updated_at=stamp,
            status=PlanStatus.COMPLETED,
            revision=revision,
            change_reason=CHANGE_REASON_MISSION_COMPLETED,
            latest_changes=[
                CHANGE_REASON_MISSION_COMPLETED,
                f"status {target.status.value} → {PlanStatus.COMPLETED.value}",
            ],
        )
        self._active_plan = completed
        if revision != target.revision:
            logger.info(
                "PLAN_UPDATED goal=%s project=%s mission=%s revision=%s reason=%s",
                completed.current_goal,
                completed.current_project,
                completed.current_mission,
                completed.revision,
                completed.change_reason,
            )
            logger.info("PLAN_REVISION revision=%s", completed.revision)
        logger.info(
            "PLAN_COMPLETED goal=%s project=%s mission=%s revision=%s",
            completed.current_goal,
            completed.current_project,
            completed.current_mission,
            completed.revision,
        )
        return completed

    def create_plan(
        self,
        message: str,
        *,
        mission: dict | None = None,
        state: dict | None = None,
    ) -> StructuredPlan:
        """Build a Phase 8 structured plan from user intent and mission context."""
        mission = mission or {}
        state = state or {}
        domain = self._detect_domain(message, mission)
        mission_step = mission.get("current_step") if mission.get("active") else None
        goal = self._resolve_goal(message, mission, state)

        if mission_step:
            steps = self._plan_for_mission_step(message, mission_step, domain)
            focus = mission_step
        else:
            steps = self._plan_for_open_goal(message, domain)
            focus = steps[0].description if steps else goal

        return StructuredPlan(
            goal=goal,
            steps=steps,
            current_focus=focus,
            mission_step=mission_step,
            domain=domain,
        )

    @staticmethod
    def _emit_evolution(plan: Plan, mode: str) -> None:
        if mode == EVOLVE_CREATED:
            logger.info(
                "PLAN_CREATED goal=%s project=%s mission=%s priority=%s "
                "actions=%s blocked=%s revision=%s reason=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.priority_score,
                len(plan.next_actions),
                bool(plan.blocked_reason),
                plan.revision,
                plan.change_reason,
            )
            logger.info("PLAN_REVISION revision=%s", plan.revision)
            return

        if mode == EVOLVE_REBUILT:
            logger.info(
                "PLAN_REBUILT goal=%s project=%s mission=%s priority=%s "
                "actions=%s blocked=%s revision=%s reason=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.priority_score,
                len(plan.next_actions),
                bool(plan.blocked_reason),
                plan.revision,
                plan.change_reason,
            )
        elif mode == EVOLVE_UPDATED:
            logger.info(
                "PLAN_UPDATED goal=%s project=%s mission=%s priority=%s "
                "actions=%s blocked=%s revision=%s reason=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.priority_score,
                len(plan.next_actions),
                bool(plan.blocked_reason),
                plan.revision,
                plan.change_reason,
            )
        elif mode == EVOLVE_REFRESHED:
            logger.info(
                "PLAN_REFRESHED goal=%s project=%s mission=%s revision=%s reason=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.revision,
                plan.change_reason,
            )

        logger.info("PLAN_REVISION revision=%s", plan.revision)

    @staticmethod
    def _emit_status_diagnostics(plan: Plan) -> None:
        if plan.is_blocked:
            logger.info(
                "PLAN_BLOCKED goal=%s project=%s mission=%s reason=%s revision=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.blocked_reason,
                plan.revision,
            )
        if plan.status == PlanStatus.COMPLETED:
            logger.info(
                "PLAN_COMPLETED goal=%s project=%s mission=%s revision=%s",
                plan.current_goal,
                plan.current_project,
                plan.current_mission,
                plan.revision,
            )

    def _detect_domain(self, message: str, mission: dict) -> str:
        lowered = message.lower()
        title = (mission.get("title") or "").lower()
        combined = f"{lowered} {title}"
        best_domain = "general"
        best_score = 0
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > best_score:
                best_score = score
                best_domain = domain
        return best_domain

    def _resolve_goal(self, message: str, mission: dict, state: dict) -> str:
        if mission.get("active") and mission.get("objective"):
            return str(mission["objective"])
        project = state.get("active_project")
        if project:
            return f"Avancer sur {project} : {message}"
        return message

    def _plan_for_mission_step(
        self,
        message: str,
        mission_step: str,
        domain: str,
    ) -> list[PlanStep]:
        """Steps scoped to the active mission step."""
        base = [
            PlanStep(
                1,
                f"Comprendre la demande dans le contexte de : {mission_step}",
                linked_mission_step=mission_step,
                action_type="analyze",
            ),
            PlanStep(
                2,
                f"Exécuter l'étape mission : {mission_step}",
                linked_mission_step=mission_step,
                action_type=self._domain_action(domain),
            ),
            PlanStep(
                3,
                "Vérifier le résultat et proposer la suite",
                linked_mission_step=mission_step,
                action_type="verify",
            ),
        ]
        if domain == "coding":
            base.insert(
                2,
                PlanStep(
                    2,
                    "Identifier les fichiers et modules concernés",
                    linked_mission_step=mission_step,
                    action_type="inspect",
                ),
            )
            for idx, step in enumerate(base, start=1):
                step.order = idx
        return base

    def _plan_for_open_goal(self, message: str, domain: str) -> list[PlanStep]:
        """Generic plan when no mission is active."""
        return [
            PlanStep(1, f"Comprendre l'objectif : {message}", action_type="analyze"),
            PlanStep(
                2,
                "Identifier les informations et ressources nécessaires",
                action_type="gather",
            ),
            PlanStep(
                3,
                f"Exécuter via {self._domain_action(domain)}",
                action_type=self._domain_action(domain),
            ),
            PlanStep(4, "Vérifier le résultat", action_type="verify"),
        ]

    @staticmethod
    def _domain_action(domain: str) -> str:
        mapping = {
            "trading": "trade_analyze",
            "coding": "code",
            "research": "research",
            "planning": "plan",
        }
        return mapping.get(domain, "respond")

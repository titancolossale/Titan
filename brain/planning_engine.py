# =====================================
# Titan Planning Engine
# =====================================

"""Structured mission-linked planning for Brain pipeline (Phase 8 — P8-031)."""

from __future__ import annotations

from brain.planning_models import PlanStep, StructuredPlan

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trading": ("trading", "backtest", "nq", "robot", "marché", "position"),
    "coding": ("code", "python", "fonction", "fichier", "script", "module"),
    "research": ("recherche", "analyser", "information", "étude", "etude"),
    "planning": ("plan", "organiser", "étapes", "roadmap", "projet"),
}


class PlanningEngine:
    """Produce structured plans linked to active mission steps."""

    def create_plan(
        self,
        message: str,
        *,
        mission: dict | None = None,
        state: dict | None = None,
    ) -> StructuredPlan:
        """Build a structured plan from user intent and mission context."""
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

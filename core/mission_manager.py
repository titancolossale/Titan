# =====================================
# Titan Mission Manager
# =====================================

"""Mission lifecycle persistence — facade over MissionRuntime (Mission Runtime V1)."""

from __future__ import annotations

import json
from pathlib import Path

from core.mission_migrator import SCHEMA_VERSION, default_schema, migrate
from core.mission_models import Mission, MissionPriority, MissionState
from core.mission_runtime import MissionRuntime


class MissionManager:
    """Persist multi-step missions with completed-step history.

    Delegates runtime lifecycle to ``MissionRuntime`` while preserving the
    v2-compatible API used by Brain pipeline stages and REPL commands.
    """

    def __init__(self, file_path: str | Path = "data/titan_mission.json") -> None:
        self.file_path = Path(file_path)
        self._runtime = MissionRuntime(file_path=self.file_path)
        self.mission = self._runtime.get_legacy_mission_view()

    def load_mission(self) -> dict:
        self._runtime = MissionRuntime(file_path=self.file_path)
        self.mission = self._runtime.get_legacy_mission_view()
        return self.mission

    def save_mission(self) -> None:
        self._runtime._sync_legacy_view()
        self._runtime._save_document()
        self.mission = self._runtime.get_legacy_mission_view()

    @property
    def runtime(self) -> MissionRuntime:
        """Mission Runtime V1 engine for Brain API and integrations."""
        return self._runtime

    def create_mission(self, title: str, objective: str, steps: list[str]) -> Mission:
        mission = self._runtime.create_mission(
            title,
            objective,
            list(steps),
            state=MissionState.READY,
        )
        self.mission = self._runtime.get_legacy_mission_view()
        return mission

    def get_mission(self) -> dict:
        self.mission = self._runtime.get_legacy_mission_view()
        return self.mission

    def complete_current_step(self) -> None:
        """Advance mission by recording current step in history — never mutates steps list."""
        self._runtime.complete_current_step()
        self.mission = self._runtime.get_legacy_mission_view()

    def cancel_mission(self) -> None:
        """Mark active mission as cancelled without deleting history."""
        self._runtime.cancel_mission()
        self.mission = self._runtime.get_legacy_mission_view()

    def _next_pending_step(self) -> str | None:
        """Return the first step not yet in completed_steps."""
        mission = self._runtime.get_active_mission()
        if mission is None:
            return None
        completed = set(mission.completed_steps)
        for step in mission.steps:
            if step not in completed:
                return step
        return None

    def format_status(self) -> str:
        """French mission status summary for REPL commands (P8-010)."""
        mission = self._runtime.get_focused_mission()
        if mission is None:
            return "Aucune mission active."

        lines = [
            f"Mission : {mission.title or 'Sans titre'}",
            f"Statut : {mission.state.value}",
            f"Objectif : {mission.objective or '—'}",
            f"Progression : {mission.progress_percent:.0f}%",
        ]
        current = mission.current_step
        if current:
            lines.append(f"Étape en cours : {current}")

        completed = mission.completed_steps
        if completed:
            lines.append(f"Étapes terminées ({len(completed)}) :")
            for step in completed:
                lines.append(f"  ✓ {step}")

        remaining = mission.remaining_steps
        if remaining:
            lines.append(f"Étapes restantes ({len(remaining)}) :")
            for step in remaining:
                marker = "→" if step == current else "·"
                lines.append(f"  {marker} {step}")

        return "\n".join(lines)

    def show_mission(self) -> str:
        return json.dumps(self.get_mission(), indent=4, ensure_ascii=False)

    def handle_command(self, message: str) -> str | None:
        """Handle mission REPL commands; return French response when matched (P8-011)."""
        lowered = message.lower().strip()

        if self._matches_command(lowered, ("statut mission", "mission status", "/mission status")):
            return self.format_status()

        if self._matches_command(
            lowered,
            ("terminer étape", "terminer etape", "complete step", "/mission complete"),
        ):
            active = self._runtime.get_focused_mission()
            if active is None or not active.is_active:
                return "Aucune mission active — rien à terminer."
            previous = active.current_step
            self.complete_current_step()
            active = self._runtime.get_focused_mission()
            if active is not None and active.is_active and active.current_step:
                return (
                    f"Étape terminée : « {previous} ».\n"
                    f"Prochaine étape : {active.current_step}"
                )
            return f"Mission terminée. Dernière étape complétée : « {previous} »."

        if self._matches_command(
            lowered,
            ("annuler mission", "cancel mission", "/mission cancel"),
        ):
            active = self._runtime.get_focused_mission()
            if active is None or not active.is_active:
                return "Aucune mission active à annuler."
            title = active.title or "Sans titre"
            self.cancel_mission()
            return f"Mission « {title} » annulée."

        return None

    def is_pure_mission_command(self, message: str) -> bool:
        """True when message is only a mission command that skips LLM (P8-011)."""
        lowered = message.lower().strip()
        pure_commands = (
            "statut mission",
            "mission status",
            "/mission status",
            "terminer étape",
            "terminer etape",
            "complete step",
            "/mission complete",
            "annuler mission",
            "cancel mission",
            "/mission cancel",
        )
        return lowered in pure_commands

    @staticmethod
    def _matches_command(lowered: str, triggers: tuple[str, ...]) -> bool:
        return any(
            lowered == trigger or lowered.startswith(f"{trigger} ")
            for trigger in triggers
        )

    def should_create_mission_from_message(self, message: str) -> bool:
        """Return True only when the message expresses explicit mission creation intent."""
        message_lower = message.lower().strip()

        prefix_triggers = (
            "nouvelle mission",
            "new mission",
            "/mission",
        )
        strong_phrases = (
            "créer une mission",
            "lancer une mission",
        )

        for phrase in strong_phrases:
            if phrase in message_lower:
                return True

        for prefix in prefix_triggers:
            if message_lower.startswith(prefix) or f" {prefix}" in message_lower:
                if prefix == "/mission" and message_lower.startswith("/mission "):
                    sub = message_lower[len("/mission "):].strip()
                    if sub in ("status", "complete", "cancel"):
                        return False
                return True

        return False

    def create_mission_from_message(self, message: str) -> dict:
        message_lower = message.lower()

        if "trading" in message_lower or "robot" in message_lower or "bot" in message_lower:
            title = "Créer un robot de trading"
            objective = message
            steps = [
                "Définir le marché et la stratégie",
                "Créer l'architecture du robot",
                "Créer le système de backtest",
                "Créer le système d'exécution",
                "Ajouter la gestion du risque",
                "Ajouter les logs et le monitoring",
                "Tester en paper trading",
            ]

        elif "titan" in message_lower:
            title = "Améliorer Titan"
            objective = message
            steps = [
                "Comprendre l'amélioration demandée",
                "Modifier l'architecture si nécessaire",
                "Ajouter ou modifier les fichiers",
                "Tester le fonctionnement",
                "Sauvegarder l'état du projet",
            ]

        else:
            title = "Mission générale"
            objective = message
            steps = [
                "Comprendre la demande",
                "Créer un plan",
                "Exécuter la première étape",
                "Vérifier le résultat",
            ]

        self.create_mission(title, objective, steps)
        return self.get_mission()

    def advance_mission(self) -> dict:
        active = self._runtime.get_active_mission()
        if active is None:
            return self.get_mission()

        self.complete_current_step()
        return self.get_mission()

    # --- Mission Runtime V1 Brain API passthrough ---

    def resume_mission(self, mission_id: str) -> Mission:
        mission = self._runtime.resume_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        return mission

    def update_mission(self, mission_id: str, **kwargs) -> Mission:
        mission = self._runtime.update_mission(mission_id, **kwargs)
        self.mission = self._runtime.get_legacy_mission_view()
        return mission

    def complete_mission(self, mission_id: str) -> Mission:
        mission = self._runtime.complete_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        return mission

    def list_active_missions(self) -> list[Mission]:
        return self._runtime.list_active_missions()

    def on_tool_execution_complete(self, **kwargs) -> Mission | None:
        mission = self._runtime.on_tool_execution_complete(**kwargs)
        self.mission = self._runtime.get_legacy_mission_view()
        return mission

# =====================================
# Titan Mission Manager
# =====================================

"""Mission lifecycle persistence with v2 step history (Phase 8 — P8-002)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.mission_migrator import default_schema, migrate


class MissionManager:
    """Persist multi-step missions with completed-step history."""

    def __init__(self, file_path: str | Path = "data/titan_mission.json") -> None:
        self.file_path = Path(file_path)
        self.mission = self.load_mission()

    def load_mission(self) -> dict:
        if not self.file_path.exists():
            return default_schema()

        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        return migrate(raw)

    def save_mission(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self.mission, file, indent=4, ensure_ascii=False)

    def create_mission(self, title: str, objective: str, steps: list[str]) -> None:
        self.mission = {
            **default_schema(),
            "active": True,
            "title": title,
            "objective": objective,
            "steps": list(steps),
            "completed_steps": [],
            "current_step": steps[0] if steps else None,
            "status": "in_progress",
        }
        self.save_mission()

    def get_mission(self) -> dict:
        return self.mission

    def complete_current_step(self) -> None:
        """Advance mission by recording current step in history — never mutates steps list."""
        if not self.mission.get("active"):
            return

        current = self.mission.get("current_step")
        if not current:
            return

        completed = self.mission.setdefault("completed_steps", [])
        if current not in completed:
            completed.append(current)

        next_step = self._next_pending_step()
        self.mission["current_step"] = next_step

        if next_step is None:
            self.mission["active"] = False
            self.mission["status"] = "completed"

        self.save_mission()

    def cancel_mission(self) -> None:
        """Mark active mission as cancelled without deleting history."""
        if not self.mission.get("active"):
            return
        self.mission["active"] = False
        self.mission["status"] = "cancelled"
        self.save_mission()

    def _next_pending_step(self) -> str | None:
        """Return the first step not yet in completed_steps."""
        completed = set(self.mission.get("completed_steps", []))
        for step in self.mission.get("steps", []):
            if step not in completed:
                return step
        return None

    def format_status(self) -> str:
        """French mission status summary for REPL commands (P8-010)."""
        mission = self.mission
        if not mission.get("active") and mission.get("status") == "idle":
            return "Aucune mission active."

        lines = [
            f"Mission : {mission.get('title') or 'Sans titre'}",
            f"Statut : {mission.get('status', 'inconnu')}",
            f"Objectif : {mission.get('objective') or '—'}",
        ]
        current = mission.get("current_step")
        if current:
            lines.append(f"Étape en cours : {current}")

        completed = mission.get("completed_steps", [])
        if completed:
            lines.append(f"Étapes terminées ({len(completed)}) :")
            for step in completed:
                lines.append(f"  ✓ {step}")

        remaining = [
            step
            for step in mission.get("steps", [])
            if step not in set(completed)
        ]
        if remaining:
            lines.append(f"Étapes restantes ({len(remaining)}) :")
            for step in remaining:
                marker = "→" if step == current else "·"
                lines.append(f"  {marker} {step}")

        return "\n".join(lines)

    def show_mission(self) -> str:
        return json.dumps(self.mission, indent=4, ensure_ascii=False)

    def handle_command(self, message: str) -> str | None:
        """Handle mission REPL commands; return French response when matched (P8-011)."""
        lowered = message.lower().strip()

        if self._matches_command(lowered, ("statut mission", "mission status", "/mission status")):
            return self.format_status()

        if self._matches_command(
            lowered,
            ("terminer étape", "terminer etape", "complete step", "/mission complete"),
        ):
            if not self.mission.get("active"):
                return "Aucune mission active — rien à terminer."
            previous = self.mission.get("current_step")
            self.complete_current_step()
            if self.mission.get("active"):
                return (
                    f"Étape terminée : « {previous} ».\n"
                    f"Prochaine étape : {self.mission.get('current_step')}"
                )
            return f"Mission terminée. Dernière étape complétée : « {previous} »."

        if self._matches_command(
            lowered,
            ("annuler mission", "cancel mission", "/mission cancel"),
        ):
            if not self.mission.get("active"):
                return "Aucune mission active à annuler."
            title = self.mission.get("title") or "Sans titre"
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
        return self.mission

    def advance_mission(self) -> dict:
        if not self.mission.get("active"):
            return self.mission

        self.complete_current_step()
        return self.mission

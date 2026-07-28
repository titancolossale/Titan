# =====================================
# Titan Mission Manager
# =====================================

"""Mission lifecycle persistence — facade over MissionRuntime (Phase 14.1).

``MissionManager`` is the single owner of every ``Mission``. Other modules must
not mutate mission documents directly. Brain wiring is intentionally unchanged
in this foundation phase.

Phase 14.2 — when a ``StateManager`` is injected, the active mission is mirrored
into ``WorkspaceState`` after every lifecycle mutation (MissionManager remains
the owner; WorkspaceState only mirrors).

Phase 14.5 — multi-mission workspace: WorkspaceState mirrors the concise mission
list plus queue/paused counts; only one mission is ACTIVE at a time.

Phase 15.1 — every mission belongs to exactly one project. When a
``ProjectManager`` is injected, ownership is validated on create/update and
mission ids are registered on the owning project.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import TITAN_MISSION_PATH
from core.mission_models import Mission, MissionPriority, MissionState
from core.mission_runtime import MissionRuntime

if TYPE_CHECKING:
    from core.project_manager import ProjectManager
    from core.state_manager import StateManager

logger = logging.getLogger(__name__)


class MissionManager:
    """Persist multi-step missions with completed-step history.

    Delegates runtime lifecycle to ``MissionRuntime`` while preserving the
    v2-compatible API used by Brain pipeline stages and REPL commands, and
    exposing the Phase 14.1 foundation API.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        state_manager: StateManager | None = None,
        project_manager: ProjectManager | None = None,
    ) -> None:
        self.file_path = (
            Path(file_path) if file_path is not None else Path(TITAN_MISSION_PATH)
        )
        self._runtime = MissionRuntime(file_path=self.file_path)
        self._state_manager = state_manager
        self._project_manager = project_manager
        self.mission = self._runtime.get_legacy_mission_view()
        if self._state_manager is not None:
            self._sync_workspace_state()

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

    # ------------------------------------------------------------------
    # Phase 14.1 foundation API
    # ------------------------------------------------------------------

    def create_mission(
        self,
        title: str,
        objective: str = "",
        steps: list[str] | None = None,
        *,
        description: str | None = None,
        priority: MissionPriority | str = MissionPriority.NORMAL,
        tags: list[str] | None = None,
        parent_mission: str | None = None,
        notes: str = "",
        current_step: str | None = None,
        state: MissionState | str = MissionState.READY,
        project_id: str | None = None,
    ) -> Mission:
        """Create a mission owned by this manager and persist it.

        Phase 15.1 — when a ProjectManager is bound, ``project_id`` is required
        (or defaults to the active project) and must reference a known project.
        """
        resolved_project_id = self._resolve_project_id(project_id)
        mission = self._runtime.create_mission(
            title,
            objective,
            list(steps or []),
            description=description,
            priority=priority,
            state=state,
            tags=tags,
            parent_mission=parent_mission,
            notes=notes,
            current_step=current_step,
            project_id=resolved_project_id,
        )
        self.mission = self._runtime.get_legacy_mission_view()
        self._register_mission_with_project(mission)
        self._sync_workspace_state()
        return mission

    def get_active_mission(self) -> Mission | None:
        """Return the focused non-terminal mission, if any."""
        return self._runtime.get_active_mission()

    def list_missions(
        self,
        *,
        status: str | MissionState | None = None,
        include_archived: bool = True,
        active_only: bool = False,
        project_id: str | None = None,
    ) -> list[Mission]:
        """List missions owned by this manager."""
        missions = self._runtime.list_missions(
            status=status,
            include_archived=include_archived,
            active_only=active_only,
        )
        if project_id is not None:
            missions = [item for item in missions if item.project_id == project_id]
        return missions

    def update_mission(self, mission_id: str, **kwargs) -> Mission:
        """Update fields on a mission and persist."""
        old_project_id: str | None = None
        if "project_id" in kwargs:
            new_project_id = kwargs.get("project_id")
            if new_project_id is not None:
                self._validate_project_ownership(str(new_project_id))
            existing = self._runtime.get_mission(mission_id)
            old_project_id = existing.project_id if existing is not None else None

        mission = self._runtime.update_mission(mission_id, **kwargs)
        self.mission = self._runtime.get_legacy_mission_view()

        if "project_id" in kwargs and self._project_manager is not None:
            new_project_id = mission.project_id
            if old_project_id and old_project_id != new_project_id:
                self._project_manager.unregister_mission(old_project_id, mission.id)
            if new_project_id:
                self._register_mission_with_project(mission)

        self._sync_workspace_state()
        return mission

    def complete_mission(self, mission_id: str) -> Mission:
        """Mark a mission completed and stamp ``completed_at``."""
        mission = self._runtime.complete_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        if mission.project_id and self._project_manager is not None:
            self._project_manager.record_completed_mission(
                mission.project_id,
                mission.id,
                mission_title=mission.title,
            )
        else:
            self._notify_project_active_mission(mission, clear=True)
        self._sync_workspace_state()
        return mission

    def pause_mission(self, mission_id: str | None = None) -> Mission:
        """Pause a mission (Phase 14.5). Clears ACTIVE focus when pausing the focus.

        Phase 16.2 — does not clear ``project.active_mission_id`` so
        ``GoalManager.resume_goal`` can restore the current mission.
        """
        mission = self._runtime.pause_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        self._sync_workspace_state()
        return mission

    def cancel_mission(self, mission_id: str | None = None) -> Mission | None:
        """Cancel a mission without deleting history."""
        mission = self._runtime.cancel_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        if mission is not None:
            self._notify_project_active_mission(mission, clear=True)
        self._sync_workspace_state()
        return mission

    def archive_mission(self, mission_id: str) -> Mission:
        """Archive a mission (retained, terminal)."""
        mission = self._runtime.archive_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        self._notify_project_active_mission(mission, clear=True)
        self._sync_workspace_state()
        return mission

    def delete_mission(self, mission_id: str) -> None:
        """Permanently delete a mission from persistence."""
        existing = self._runtime.get_mission(mission_id)
        project_id = existing.project_id if existing is not None else None
        self._runtime.delete_mission(mission_id)
        self.mission = self._runtime.get_legacy_mission_view()
        if project_id and self._project_manager is not None:
            self._project_manager.unregister_mission(project_id, mission_id)
        self._sync_workspace_state()

    # ------------------------------------------------------------------
    # Legacy / Brain-compatible API
    # ------------------------------------------------------------------

    def get_mission(self) -> dict:
        self.mission = self._runtime.get_legacy_mission_view()
        return self.mission

    def complete_current_step(self) -> None:
        """Advance mission by recording current step in history — never mutates steps list."""
        self._runtime.complete_current_step()
        self.mission = self._runtime.get_legacy_mission_view()
        self._sync_workspace_state()

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
            f"Statut : {mission.status}",
            f"Objectif : {mission.description or mission.objective or '—'}",
            f"Progression : {mission.progress:.0f}%",
        ]
        current = mission.current_step
        if current:
            lines.append(f"Étape en cours : {current}")
        if mission.next_step:
            lines.append(f"Prochaine étape : {mission.next_step}")

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
        if mission.project_id and self._project_manager is not None:
            self._project_manager.set_active_mission(
                mission.project_id,
                mission.id,
                progress=float(mission.progress),
            )
        self._sync_workspace_state()
        return mission

    def list_active_missions(self) -> list[Mission]:
        return self._runtime.list_active_missions()

    def on_tool_execution_complete(self, **kwargs) -> Mission | None:
        mission = self._runtime.on_tool_execution_complete(**kwargs)
        self.mission = self._runtime.get_legacy_mission_view()
        self._sync_workspace_state()
        return mission

    # ------------------------------------------------------------------
    # Phase 15.1 — project ownership
    # ------------------------------------------------------------------

    def bind_project_manager(self, project_manager: ProjectManager | None) -> None:
        """Attach or replace the ProjectManager used for ownership validation."""
        self._project_manager = project_manager

    def _resolve_project_id(self, project_id: str | None) -> str | None:
        """Validate / default project ownership when ProjectManager is bound."""
        if self._project_manager is None:
            return project_id

        if project_id is None:
            active = self._project_manager.get_active_project()
            if active is None:
                # Ensure every mission has a project without breaking Brain flows
                # that create missions before an explicit ProjectManager create.
                default_name = "Titan"
                if self._state_manager is not None:
                    snap = self._state_manager.snapshot()
                    if snap.active_project:
                        default_name = str(snap.active_project)
                active = self._project_manager.create_project(default_name)
            project_id = active.id

        self._validate_project_ownership(project_id)
        return project_id

    def _validate_project_ownership(self, project_id: str) -> None:
        if self._project_manager is None:
            return
        if not self._project_manager.has_project(project_id):
            raise ValueError(
                f"Unknown project id for mission ownership: {project_id}"
            )

    def _register_mission_with_project(self, mission: Mission) -> None:
        if self._project_manager is None or not mission.project_id:
            return
        self._project_manager.register_mission(
            mission.project_id,
            mission.id,
            set_active=True,
            mission_progress=float(mission.progress),
        )

    def _notify_project_active_mission(
        self,
        mission: Mission,
        *,
        clear: bool,
    ) -> None:
        if self._project_manager is None or not mission.project_id:
            return
        self._project_manager.set_active_mission(
            mission.project_id,
            None if clear else mission.id,
            progress=float(mission.progress),
        )

    # ------------------------------------------------------------------
    # Phase 14.2 — WorkspaceState mirror (MissionManager owns truth)
    # ------------------------------------------------------------------

    def bind_state_manager(self, state_manager: StateManager | None) -> None:
        """Attach or replace the WorkspaceState mirror target."""
        self._state_manager = state_manager
        if self._state_manager is not None:
            self._sync_workspace_state()

    def _sync_workspace_state(self) -> None:
        """Mirror active mission + concise mission list into WorkspaceState.

        MissionManager remains the owner of mission truth. WorkspaceState stores
        a concise multi-mission list and counts so Brain can read once per turn
        without reloading the mission document.
        """
        if self._state_manager is None:
            return

        logger.info("MISSION_SYNC_BEGIN")
        previous_id = self._state_manager.snapshot().active_mission_id
        active = self.get_active_mission()
        all_missions = self.list_missions(include_archived=True)
        focused_id = active.id if active is not None else None
        mission_entries = [
            {
                "id": item.id,
                "title": item.title,
                "status": item.workspace_status(
                    is_focused=focused_id is not None and item.id == focused_id
                ),
                "progress": float(item.progress),
            }
            for item in all_missions
        ]
        queue_count = sum(
            1 for item in all_missions if item.state == MissionState.QUEUED
        )
        paused_count = sum(
            1 for item in all_missions if item.state == MissionState.PAUSED
        )

        if active is None:
            patch = {
                "active_mission_id": None,
                "active_mission_title": None,
                "active_mission_status": None,
                "active_mission_progress": None,
                "active_mission_priority": None,
                "active_mission_stage": None,
                "active_mission": None,
                # Phase 14.4 — clear resume slice with the active mission
                "active_mission_last_completed_step": None,
                "active_mission_last_summary": None,
                "active_mission_progress_updated_at": None,
                "active_mission_current_objective": None,
                # Phase 14.5 — multi-mission workspace mirror
                "missions": mission_entries,
                "mission_queue_count": queue_count,
                "paused_mission_count": paused_count,
            }
            new_id: str | None = None
        else:
            priority = (
                active.priority.value
                if hasattr(active.priority, "value")
                else str(active.priority)
            )
            completed = list(active.completed_steps or [])
            objective = (
                active.current_step
                or active.next_step
                or active.objective
                or None
            )
            patch = {
                "active_mission_id": active.id,
                "active_mission_title": active.title,
                "active_mission_status": active.status,
                "active_mission_progress": float(active.progress),
                "active_mission_priority": priority,
                "active_mission_stage": active.current_step,
                "active_mission": active.title,
                # Phase 14.4 — structural resume fields (summary set by think cycle)
                "active_mission_last_completed_step": (
                    completed[-1] if completed else None
                ),
                "active_mission_current_objective": objective,
                # Phase 14.5 — multi-mission workspace mirror
                "missions": mission_entries,
                "mission_queue_count": queue_count,
                "paused_mission_count": paused_count,
            }
            new_id = active.id

        if previous_id != new_id:
            logger.info(
                "MISSION_ACTIVE_CHANGED previous=%s new=%s",
                previous_id,
                new_id,
            )
            logger.info(
                "MISSION_SWITCHED previous=%s new=%s",
                previous_id,
                new_id,
            )

        self._state_manager.update(patch)
        logger.info("MISSION_SYNC_DONE")

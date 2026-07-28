# =====================================
# Titan Goal Manager
# =====================================

"""Goal lifecycle persistence — Phase 16.1–16.2 Goal Manager.

``GoalManager`` is the single owner of every workspace-level ``Goal``. Goals
group projects; only one goal may be ACTIVE at a time. When a ``StateManager``
is injected, the active goal and concise goal list are mirrored into
``WorkspaceState`` after every lifecycle mutation (GoalManager remains the
owner; WorkspaceState only mirrors).

Phase 16.2 — goal progress is computed from contained projects (single scan).
``resume_goal`` restores the current project, mission, and workspace mirror.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import TITAN_GOAL_PATH
from core.goal_models import (
    Goal,
    GoalPriority,
    GoalProgress,
    GoalState,
    compute_goal_progress_from_projects,
    workspace_goal_entry,
)

if TYPE_CHECKING:
    from core.mission_manager import MissionManager
    from core.project_manager import ProjectManager
    from core.state_manager import StateManager

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now().astimezone()


def default_schema() -> dict[str, Any]:
    """Return the default persisted goal document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "active_goal_id": None,
        "goals": {},
    }


class GoalManager:
    """Persist multi-project goals with single-ACTIVE workspace focus.

    Owns goal truth under ``TITAN_GOAL_PATH``. Mirrors a concise slice into
    ``WorkspaceState`` so Brain can read goal awareness from the same
    StateManager load used for projects and missions — no duplicated goal
    lookups.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        state_manager: StateManager | None = None,
        project_manager: ProjectManager | None = None,
        mission_manager: MissionManager | None = None,
    ) -> None:
        self.file_path = (
            Path(file_path) if file_path is not None else Path(TITAN_GOAL_PATH)
        )
        self._lock = threading.RLock()
        self._state_manager = state_manager
        self._project_manager = project_manager
        self._mission_manager = mission_manager
        self._document: dict[str, Any] = default_schema()
        self._load_document()
        if self._state_manager is not None:
            self._sync_workspace_state()

    # ------------------------------------------------------------------
    # Phase 16.1 foundation API
    # ------------------------------------------------------------------

    def create_goal(
        self,
        name: str,
        description: str = "",
        *,
        priority: GoalPriority | str = GoalPriority.NORMAL,
        status: GoalState | str = GoalState.ACTIVE,
        aliases: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> Goal:
        """Create a goal and make it the ACTIVE focus (single ACTIVE rule).

        Phase 16.3 — ``aliases`` / ``keywords`` persist for automatic matching.
        """
        with self._lock:
            now = _utc_now()
            goal_id = str(uuid.uuid4())

            if isinstance(priority, str):
                priority = GoalPriority(priority.strip().upper())
            if isinstance(status, str):
                status = GoalState(status.strip().upper())

            previous_id = self._document.get("active_goal_id")
            # Only one ACTIVE goal — demote the previous focus to PAUSED.
            if status == GoalState.ACTIVE and previous_id:
                previous = self._goals_map().get(str(previous_id))
                if previous is not None and previous.status == GoalState.ACTIVE.value:
                    paused = self._replace_fields(
                        previous,
                        status=GoalState.PAUSED.value,
                        updated_at=now,
                    )
                    self._store_goal(paused)

            goal = Goal(
                id=goal_id,
                name=name,
                description=description or "",
                status=status.value,
                priority=priority,
                created_at=now,
                updated_at=now,
                progress=0.0,
                project_ids=[],
                active_project_id=None,
                aliases=[
                    str(item).strip() for item in (aliases or []) if str(item).strip()
                ],
                keywords=[
                    str(item).strip() for item in (keywords or []) if str(item).strip()
                ],
            )
            self._store_goal(goal)
            if status == GoalState.ACTIVE:
                self._document["active_goal_id"] = goal_id
            elif self._document.get("active_goal_id") is None:
                self._document["active_goal_id"] = None

            self._save_document()
            logger.info(
                "GOAL_CREATED id=%s name=%r status=%s",
                goal_id,
                name,
                status.value,
            )
            if status == GoalState.ACTIVE and previous_id and previous_id != goal_id:
                logger.info(
                    "GOAL_SWITCHED previous=%s new=%s",
                    previous_id,
                    goal_id,
                )

        self._sync_workspace_state()
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        """Return a goal by id, or None when missing."""
        with self._lock:
            return self._goals_map().get(goal_id)

    def get_active_goal(self) -> Goal | None:
        """Return the single ACTIVE goal, if any."""
        with self._lock:
            active_id = self._document.get("active_goal_id")
            if not active_id:
                return None
            goal = self._goals_map().get(str(active_id))
            if goal is None:
                return None
            if goal.status != GoalState.ACTIVE.value:
                return None
            return goal

    def list_goals(
        self,
        *,
        status: str | GoalState | None = None,
        include_archived: bool = True,
    ) -> list[Goal]:
        """List goals owned by this manager."""
        with self._lock:
            goals = list(self._goals_map().values())

        if status is not None:
            status_value = (
                status.value if isinstance(status, GoalState) else str(status).upper()
            )
            goals = [item for item in goals if item.status == status_value]

        if not include_archived:
            goals = [
                item for item in goals if item.status != GoalState.ARCHIVED.value
            ]

        goals.sort(key=lambda item: item.updated_at, reverse=True)
        return goals

    def pause_goal(self, goal_id: str | None = None) -> Goal:
        """Pause a goal. Clears ACTIVE focus when pausing the active goal."""
        with self._lock:
            goal = self._resolve_target(goal_id)
            now = _utc_now()
            updated = self._replace_fields(
                goal,
                status=GoalState.PAUSED.value,
                updated_at=now,
            )
            self._store_goal(updated)
            if self._document.get("active_goal_id") == updated.id:
                self._document["active_goal_id"] = None
            self._save_document()
            logger.info("GOAL_PAUSED id=%s name=%r", updated.id, updated.name)

        self._sync_workspace_state()
        return updated

    def resume_goal(self, goal_id: str) -> Goal:
        """Resume a goal as the single ACTIVE focus and restore nested context.

        Phase 16.2 — automatically restores the goal's current project, that
        project's current mission, and the WorkspaceState mirror. No duplicated
        GoalManager / ProjectManager / MissionManager lookups beyond the one
        restore chain.
        """
        with self._lock:
            goal = self._require_goal(goal_id)
            if goal.status == GoalState.ARCHIVED.value:
                raise ValueError(f"Cannot resume archived goal: {goal_id}")
            if goal.status == GoalState.COMPLETED.value:
                raise ValueError(f"Cannot resume completed goal: {goal_id}")

            now = _utc_now()
            previous_id = self._document.get("active_goal_id")
            if previous_id and previous_id != goal_id:
                previous = self._goals_map().get(str(previous_id))
                if previous is not None and previous.status == GoalState.ACTIVE.value:
                    paused = self._replace_fields(
                        previous,
                        status=GoalState.PAUSED.value,
                        updated_at=now,
                    )
                    self._store_goal(paused)

            updated = self._replace_fields(
                goal,
                status=GoalState.ACTIVE.value,
                updated_at=now,
            )
            self._store_goal(updated)
            self._document["active_goal_id"] = updated.id
            self._save_document()
            active_project_id = updated.active_project_id

        # Restore project + mission outside the goal lock (managers own their locks).
        restored_project_id: str | None = None
        restored_mission_id: str | None = None
        if active_project_id and self._project_manager is not None:
            project = self._project_manager.get_project(active_project_id)
            if project is not None:
                if project.status != "ACTIVE":
                    project = self._project_manager.resume_project(active_project_id)
                restored_project_id = project.id
                mission_id = project.active_mission_id
                if mission_id and self._mission_manager is not None:
                    self._mission_manager.resume_mission(mission_id)
                    restored_mission_id = mission_id

        # Refresh progress from contained projects (single scan) then mirror once.
        self.refresh_progress(updated.id)
        logger.info(
            "GOAL_RESUMED id=%s name=%r project=%s mission=%s",
            updated.id,
            updated.name,
            restored_project_id,
            restored_mission_id,
        )
        if previous_id and previous_id != updated.id:
            logger.info(
                "GOAL_SWITCHED previous=%s new=%s",
                previous_id,
                updated.id,
            )

        result = self.get_goal(updated.id)
        return result if result is not None else updated

    def complete_goal(self, goal_id: str) -> Goal:
        """Mark a goal completed and clear ACTIVE focus when needed."""
        with self._lock:
            goal = self._require_goal(goal_id)
            now = _utc_now()
            updated = self._replace_fields(
                goal,
                status=GoalState.COMPLETED.value,
                progress=100.0,
                updated_at=now,
            )
            self._store_goal(updated)
            if self._document.get("active_goal_id") == updated.id:
                self._document["active_goal_id"] = None
            self._save_document()
            logger.info(
                "GOAL_COMPLETED id=%s name=%r",
                updated.id,
                updated.name,
            )

        self._sync_workspace_state()
        return updated

    def archive_goal(self, goal_id: str) -> Goal:
        """Archive a goal (retained, terminal)."""
        with self._lock:
            goal = self._require_goal(goal_id)
            now = _utc_now()
            updated = self._replace_fields(
                goal,
                status=GoalState.ARCHIVED.value,
                updated_at=now,
            )
            self._store_goal(updated)
            if self._document.get("active_goal_id") == updated.id:
                self._document["active_goal_id"] = None
            self._save_document()
            logger.info(
                "GOAL_ARCHIVED id=%s name=%r",
                updated.id,
                updated.name,
            )

        self._sync_workspace_state()
        return updated

    def delete_goal(self, goal_id: str) -> None:
        """Permanently delete a goal from persistence."""
        with self._lock:
            self._require_goal(goal_id)
            goals = self._document.setdefault("goals", {})
            del goals[goal_id]
            if self._document.get("active_goal_id") == goal_id:
                self._document["active_goal_id"] = None
            self._save_document()
            logger.info("GOAL_DELETED id=%s", goal_id)

        self._sync_workspace_state()

    def has_goal(self, goal_id: str) -> bool:
        """Return True when the goal id is owned by this manager."""
        with self._lock:
            return goal_id in self._goals_map()

    def register_project(
        self,
        goal_id: str,
        project_id: str,
        *,
        set_active: bool = False,
        project_progress: float | None = None,
    ) -> Goal:
        """Attach a project id to a goal (ProjectManager ownership hook).

        Phase 16.2 — progress is recomputed from all contained projects after
        registration (``project_progress`` is ignored; kept for call-site compat).
        """
        del project_progress  # Progress comes from a single project scan.
        with self._lock:
            goal = self._require_goal(goal_id)
            project_ids = list(goal.project_ids)
            if project_id not in project_ids:
                project_ids.append(project_id)
            kwargs: dict[str, Any] = {
                "project_ids": project_ids,
                "updated_at": _utc_now(),
            }
            if set_active:
                kwargs["active_project_id"] = project_id
            updated = self._replace_fields(goal, **kwargs)
            self._store_goal(updated)
            self._save_document()

        self.refresh_progress(goal_id)
        result = self.get_goal(goal_id)
        return result if result is not None else updated

    def unregister_project(self, goal_id: str, project_id: str) -> Goal | None:
        """Detach a project id from a goal when the project is deleted."""
        with self._lock:
            goal = self._goals_map().get(goal_id)
            if goal is None:
                return None
            project_ids = [item for item in goal.project_ids if item != project_id]
            active_project_id = goal.active_project_id
            if active_project_id == project_id:
                active_project_id = None
            updated = self._replace_fields(
                goal,
                project_ids=project_ids,
                active_project_id=active_project_id,
                updated_at=_utc_now(),
            )
            self._store_goal(updated)
            self._save_document()

        self.refresh_progress(goal_id)
        return self.get_goal(goal_id)

    def set_active_project(
        self,
        goal_id: str,
        project_id: str | None,
        *,
        progress: float | None = None,
    ) -> Goal:
        """Update the goal's active project pointer.

        Phase 16.2 — optional ``progress`` is ignored; progress is refreshed from
        all contained projects so a single project mutation cannot skew the goal.
        """
        del progress
        with self._lock:
            goal = self._require_goal(goal_id)
            updated = self._replace_fields(
                goal,
                active_project_id=project_id,
                updated_at=_utc_now(),
            )
            self._store_goal(updated)
            self._save_document()

        self.refresh_progress(goal_id)
        result = self.get_goal(goal_id)
        return result if result is not None else updated

    def update_progress(self, goal_id: str, progress: float) -> Goal:
        """Set stored goal progress (0–100). Prefer ``refresh_progress`` when projects exist."""
        with self._lock:
            goal = self._require_goal(goal_id)
            updated = self._replace_fields(
                goal,
                progress=max(0.0, min(100.0, float(progress))),
                updated_at=_utc_now(),
            )
            self._store_goal(updated)
            self._save_document()
            logger.info(
                "GOAL_PROGRESS_UPDATED id=%s progress=%s",
                updated.id,
                updated.progress,
            )

        self._sync_workspace_state()
        return updated

    # ------------------------------------------------------------------
    # Phase 16.2 — progress from projects
    # ------------------------------------------------------------------

    def get_progress(self, goal_id: str | None = None) -> GoalProgress:
        """Return progress metrics for a goal (active goal when id omitted)."""
        with self._lock:
            goal = self._resolve_target(goal_id) if goal_id is None else self._require_goal(
                goal_id
            )
            return self._compute_progress(goal)

    def refresh_progress(self, goal_id: str) -> GoalProgress:
        """Recompute and persist goal progress from contained projects (one scan)."""
        with self._lock:
            goal = self._require_goal(goal_id)
            snapshot = self._compute_progress(goal)
            now = _utc_now()
            updated = self._replace_fields(
                goal,
                progress=float(snapshot.progress),
                updated_at=now,
            )
            self._store_goal(updated)
            self._save_document()

        logger.info(
            "GOAL_PROGRESS_UPDATED id=%s progress=%s completed=%s active=%s "
            "paused=%s total=%s last_activity=%s",
            goal_id,
            snapshot.progress,
            snapshot.completed_projects,
            snapshot.active_projects,
            snapshot.paused_projects,
            snapshot.total_projects,
            snapshot.last_activity.isoformat() if snapshot.last_activity else None,
        )
        self._sync_workspace_state()
        return snapshot

    def _compute_progress(self, goal: Goal) -> GoalProgress:
        """Single scan of the goal's projects — no full registry walk."""
        projects = self._collect_goal_projects(goal)
        return compute_goal_progress_from_projects(
            projects,
            fallback_activity=goal.updated_at,
        )

    def _collect_goal_projects(self, goal: Goal) -> list[Any]:
        """Collect projects for ``goal.project_ids`` once (no duplicated scans)."""
        if not goal.project_ids:
            return []
        if self._project_manager is not None:
            collected: list[Any] = []
            for project_id in goal.project_ids:
                project = self._project_manager.get_project(project_id)
                if project is not None:
                    collected.append(project)
            return collected

        # Fallback: WorkspaceState.projects entries matching goal project ids.
        if self._state_manager is None:
            return []
        snap = self._state_manager.snapshot()
        wanted = set(goal.project_ids)
        collected = []
        for entry in snap.projects or []:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if entry_id is None or str(entry_id) not in wanted:
                continue
            collected.append(
                type(
                    "ProjectSlice",
                    (),
                    {
                        "id": str(entry_id),
                        "status": str(entry.get("status") or ""),
                        "progress": float(entry.get("progress") or 0.0),
                        "updated_at": goal.updated_at,
                    },
                )()
            )
        return collected

    # ------------------------------------------------------------------
    # WorkspaceState mirror (GoalManager owns truth)
    # ------------------------------------------------------------------

    def bind_state_manager(self, state_manager: StateManager | None) -> None:
        """Attach or replace the WorkspaceState mirror target."""
        self._state_manager = state_manager
        if self._state_manager is not None:
            self._sync_workspace_state()

    def bind_project_manager(self, project_manager: ProjectManager | None) -> None:
        """Attach ProjectManager used for progress scans and resume restore."""
        self._project_manager = project_manager

    def bind_mission_manager(self, mission_manager: MissionManager | None) -> None:
        """Attach MissionManager used for resume restore of the active mission."""
        self._mission_manager = mission_manager

    def _sync_workspace_state(self) -> None:
        """Mirror active goal + progress/resume slice into WorkspaceState.

        GoalManager remains the owner of goal truth. WorkspaceState stores
        ``goals[]`` and ``active_goal_*`` so Brain can read once per turn
        from the single StateManager load — no duplicated goal lookups.
        """
        if self._state_manager is None:
            return

        logger.info("GOAL_SYNC_BEGIN")
        snap = self._state_manager.snapshot()
        previous_id = snap.active_goal_id
        active = self.get_active_goal()
        all_goals = self.list_goals(include_archived=True)
        goal_entries = [workspace_goal_entry(item) for item in all_goals]

        if active is None:
            patch: dict[str, Any] = {
                "active_goal_id": None,
                "active_goal": None,
                "active_goal_status": None,
                "active_goal_progress": None,
                "active_goal_completed_projects": 0,
                "active_goal_active_projects": 0,
                "active_goal_paused_projects": 0,
                "active_goal_total_projects": 0,
                "active_goal_last_activity": None,
                "active_goal_current_project": None,
                "active_goal_current_mission": None,
                "active_goal_last_summary": None,
                "active_goal_progress_updated_at": None,
                "goals": goal_entries,
            }
            new_id: str | None = None
        else:
            progress_snap = self._compute_progress(active)
            current_project = snap.active_project
            current_mission = (
                snap.active_mission_title
                or snap.active_mission
                or snap.active_project_active_mission
            )
            if active.active_project_id and self._project_manager is not None:
                project = self._project_manager.get_project(active.active_project_id)
                if project is not None:
                    current_project = project.name
                    if project.active_mission_id and (
                        not current_mission
                        or snap.active_project_id == project.id
                    ):
                        current_mission = (
                            snap.active_mission_title
                            or snap.active_mission
                            or snap.active_project_active_mission
                            or current_mission
                        )

            patch = {
                "active_goal_id": active.id,
                "active_goal": active.name,
                "active_goal_status": active.status,
                "active_goal_progress": float(progress_snap.progress),
                "active_goal_completed_projects": progress_snap.completed_projects,
                "active_goal_active_projects": progress_snap.active_projects,
                "active_goal_paused_projects": progress_snap.paused_projects,
                "active_goal_total_projects": progress_snap.total_projects,
                "active_goal_last_activity": (
                    progress_snap.last_activity.isoformat()
                    if progress_snap.last_activity is not None
                    else None
                ),
                "active_goal_current_project": current_project,
                "active_goal_current_mission": current_mission,
                "goals": goal_entries,
            }
            new_id = active.id

        if previous_id != new_id:
            logger.info(
                "GOAL_ACTIVE_CHANGED previous=%s new=%s",
                previous_id,
                new_id,
            )
            if previous_id is not None or new_id is not None:
                logger.info(
                    "GOAL_SWITCHED previous=%s new=%s",
                    previous_id,
                    new_id,
                )
            if previous_id is not None and new_id is not None and previous_id != new_id:
                patch["active_goal_last_summary"] = None
                patch["active_goal_progress_updated_at"] = None

        self._state_manager.update(patch)
        logger.info(
            "GOAL_SYNC_DONE active_id=%s count=%s",
            new_id,
            len(goal_entries),
        )
        if active is not None:
            logger.info(
                "GOAL_LOADED id=%s name=%r status=%s progress=%s",
                active.id,
                active.name,
                active.status,
                active.progress,
            )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_document(self) -> None:
        if not self.file_path.exists():
            self._document = default_schema()
            return
        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            self._document = default_schema()
            return
        goals_raw = raw.get("goals", {})
        if not isinstance(goals_raw, dict):
            goals_raw = {}
        self._document = {
            "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
            "active_goal_id": raw.get("active_goal_id"),
            "goals": {
                str(key): value
                for key, value in goals_raw.items()
                if isinstance(value, dict)
            },
        }

    def _save_document(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "active_goal_id": self._document.get("active_goal_id"),
            "goals": dict(self._document.get("goals", {})),
        }
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

    def _goals_map(self) -> dict[str, Goal]:
        raw = self._document.get("goals", {})
        result: dict[str, Goal] = {}
        if not isinstance(raw, dict):
            return result
        for key, value in raw.items():
            if isinstance(value, dict):
                result[str(key)] = Goal.from_dict(value)
        return result

    def _store_goal(self, goal: Goal) -> None:
        goals = self._document.setdefault("goals", {})
        goals[goal.id] = goal.to_dict()

    def _require_goal(self, goal_id: str) -> Goal:
        goal = self._goals_map().get(goal_id)
        if goal is None:
            raise KeyError(f"Unknown goal id: {goal_id}")
        return goal

    def _resolve_target(self, goal_id: str | None) -> Goal:
        if goal_id is not None:
            return self._require_goal(goal_id)
        active = self.get_active_goal()
        if active is None:
            raise ValueError("No active goal to target")
        return active

    @staticmethod
    def _replace_fields(goal: Goal, **kwargs: Any) -> Goal:
        data = goal.to_dict()
        for key, value in kwargs.items():
            if key in {"created_at", "updated_at"} and isinstance(value, datetime):
                data[key] = value.isoformat()
            elif key == "priority" and isinstance(value, GoalPriority):
                data[key] = value.value
            elif key in {"project_ids", "aliases", "keywords"}:
                data[key] = list(value)
            else:
                data[key] = value
        return Goal.from_dict(data)

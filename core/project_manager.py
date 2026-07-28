# =====================================
# Titan Project Manager
# =====================================

"""Project lifecycle persistence — Phase 15.1 Project Manager foundation.

``ProjectManager`` is the single owner of every ``Project``. Projects group
missions; only one project may be ACTIVE at a time. When a ``StateManager`` is
injected, the active project and concise project list are mirrored into
``WorkspaceState`` after every lifecycle mutation (ProjectManager remains the
owner; WorkspaceState only mirrors).

Phase 16.1 — when a ``GoalManager`` is injected, every project belongs to
exactly one goal and ownership is validated on create.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import TITAN_PROJECT_PATH
from core.project_models import (
    Project,
    ProjectPriority,
    ProjectState,
    workspace_project_entry,
)

if TYPE_CHECKING:
    from core.goal_manager import GoalManager
    from core.state_manager import StateManager

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now().astimezone()


def default_schema() -> dict[str, Any]:
    """Return the default persisted project document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "active_project_id": None,
        "projects": {},
    }


class ProjectManager:
    """Persist multi-mission projects with single-ACTIVE workspace focus.

    Owns project truth under ``TITAN_PROJECT_PATH``. Mirrors a concise slice into
    ``WorkspaceState`` so Brain can read project awareness from the same
    StateManager load used for missions — no duplicated project lookups.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        state_manager: StateManager | None = None,
        goal_manager: GoalManager | None = None,
    ) -> None:
        self.file_path = (
            Path(file_path) if file_path is not None else Path(TITAN_PROJECT_PATH)
        )
        self._lock = threading.RLock()
        self._state_manager = state_manager
        self._goal_manager = goal_manager
        self._document: dict[str, Any] = default_schema()
        self._load_document()
        if self._state_manager is not None:
            self._sync_workspace_state()

    # ------------------------------------------------------------------
    # Phase 15.1 foundation API
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        description: str = "",
        *,
        priority: ProjectPriority | str = ProjectPriority.NORMAL,
        status: ProjectState | str = ProjectState.ACTIVE,
        aliases: list[str] | None = None,
        keywords: list[str] | None = None,
        goal_id: str | None = None,
    ) -> Project:
        """Create a project and make it the ACTIVE focus (single ACTIVE rule).

        Phase 16.1 — when a GoalManager is bound, ``goal_id`` is required
        (or defaults to the active goal / auto-created default owner).
        """
        resolved_goal_id = self._resolve_goal_id(goal_id)
        with self._lock:
            now = _utc_now()
            project_id = str(uuid.uuid4())

            if isinstance(priority, str):
                priority = ProjectPriority(priority.strip().upper())
            if isinstance(status, str):
                status = ProjectState(status.strip().upper())

            previous_id = self._document.get("active_project_id")
            # Only one ACTIVE project — demote the previous focus to PAUSED.
            if status == ProjectState.ACTIVE and previous_id:
                previous = self._projects_map().get(str(previous_id))
                if previous is not None and previous.status == ProjectState.ACTIVE.value:
                    paused = self._replace_fields(
                        previous,
                        status=ProjectState.PAUSED.value,
                        updated_at=now,
                    )
                    self._store_project(paused)

            project = Project(
                id=project_id,
                name=name,
                description=description or "",
                status=status.value,
                created_at=now,
                updated_at=now,
                progress=0.0,
                active_mission_id=None,
                mission_ids=[],
                completed_mission_ids=[],
                priority=priority,
                aliases=[str(item).strip() for item in (aliases or []) if str(item).strip()],
                keywords=[
                    str(item).strip() for item in (keywords or []) if str(item).strip()
                ],
                goal_id=resolved_goal_id,
            )
            self._store_project(project)
            if status == ProjectState.ACTIVE:
                self._document["active_project_id"] = project_id
            elif self._document.get("active_project_id") is None:
                self._document["active_project_id"] = None

            self._save_document()
            logger.info(
                "PROJECT_CREATED id=%s name=%r status=%s",
                project_id,
                name,
                status.value,
            )
            if (
                status == ProjectState.ACTIVE
                and previous_id
                and previous_id != project_id
            ):
                logger.info(
                    "PROJECT_SWITCHED previous=%s new=%s",
                    previous_id,
                    project_id,
                )

        self._register_project_with_goal(project)
        self._sync_workspace_state()
        return project

    def should_create_project_from_message(self, message: str) -> bool:
        """Return True only for explicit project-creation phrasing."""
        lowered = (message or "").lower().strip()
        phrases = (
            "créer un project",
            "cree un project",
            "crée un project",
            "créer un projet",
            "cree un projet",
            "crée un projet",
            "create a project",
            "create project",
            "new project",
            "nouveau projet",
            "nouveau project",
        )
        return any(phrase in lowered for phrase in phrases)

    @staticmethod
    def extract_named_title(message: str) -> str | None:
        """Extract an explicit project name from nommé(e)/named phrasing."""
        patterns = (
            r"nomm[ée]e?\s+[\"«']?([A-Za-z0-9][\w\-.]{2,})",
            r"named\s+[\"']?([A-Za-z0-9][\w\-.]{2,})",
            r"appel[ée]e?\s+[\"«']?([A-Za-z0-9][\w\-.]{2,})",
        )
        for pattern in patterns:
            match = re.search(pattern, message or "", flags=re.IGNORECASE)
            if match:
                title = match.group(1).strip().strip(" .")
                if title:
                    return title
        return None

    def create_project_from_message(self, message: str) -> Project:
        """Create a project from an explicit NL create request."""
        name = self.extract_named_title(message) or "Project général"
        return self.create_project(name, description=(message or "").strip())

    def get_project(self, project_id: str) -> Project | None:
        """Return a project by id, or None when missing."""
        with self._lock:
            return self._projects_map().get(project_id)

    def get_active_project(self) -> Project | None:
        """Return the single ACTIVE project, if any."""
        with self._lock:
            active_id = self._document.get("active_project_id")
            if not active_id:
                return None
            project = self._projects_map().get(str(active_id))
            if project is None:
                return None
            if project.status != ProjectState.ACTIVE.value:
                return None
            return project

    def list_projects(
        self,
        *,
        status: str | ProjectState | None = None,
        include_archived: bool = True,
    ) -> list[Project]:
        """List projects owned by this manager."""
        with self._lock:
            projects = list(self._projects_map().values())

        if status is not None:
            status_value = (
                status.value if isinstance(status, ProjectState) else str(status).upper()
            )
            projects = [item for item in projects if item.status == status_value]

        if not include_archived:
            projects = [
                item for item in projects if item.status != ProjectState.ARCHIVED.value
            ]

        projects.sort(key=lambda item: item.updated_at, reverse=True)
        return projects

    def pause_project(self, project_id: str | None = None) -> Project:
        """Pause a project. Clears ACTIVE focus when pausing the active project."""
        with self._lock:
            project = self._resolve_target(project_id)
            now = _utc_now()
            updated = self._replace_fields(
                project,
                status=ProjectState.PAUSED.value,
                updated_at=now,
            )
            self._store_project(updated)
            if self._document.get("active_project_id") == updated.id:
                self._document["active_project_id"] = None
            self._save_document()
            logger.info("PROJECT_PAUSED id=%s name=%r", updated.id, updated.name)

        # Phase 16.2 — keep goal.active_project_id so resume_goal can restore.
        # Only refresh progress; do not clear the goal's project pointer on pause.
        self._notify_goal_progress(updated)
        self._sync_workspace_state()
        return updated

    def resume_project(self, project_id: str) -> Project:
        """Resume a project as the single ACTIVE focus."""
        with self._lock:
            project = self._require_project(project_id)
            if project.status == ProjectState.ARCHIVED.value:
                raise ValueError(f"Cannot resume archived project: {project_id}")
            if project.status == ProjectState.COMPLETED.value:
                raise ValueError(f"Cannot resume completed project: {project_id}")

            now = _utc_now()
            previous_id = self._document.get("active_project_id")
            if previous_id and previous_id != project_id:
                previous = self._projects_map().get(str(previous_id))
                if (
                    previous is not None
                    and previous.status == ProjectState.ACTIVE.value
                ):
                    paused = self._replace_fields(
                        previous,
                        status=ProjectState.PAUSED.value,
                        updated_at=now,
                    )
                    self._store_project(paused)

            updated = self._replace_fields(
                project,
                status=ProjectState.ACTIVE.value,
                updated_at=now,
            )
            self._store_project(updated)
            self._document["active_project_id"] = updated.id
            self._save_document()
            logger.info("PROJECT_RESUMED id=%s name=%r", updated.id, updated.name)
            if previous_id and previous_id != updated.id:
                logger.info(
                    "PROJECT_SWITCHED previous=%s new=%s",
                    previous_id,
                    updated.id,
                )

        self._notify_goal_active_project(updated, clear=False)
        self._sync_workspace_state()
        return updated

    def complete_project(self, project_id: str) -> Project:
        """Mark a project completed and clear ACTIVE focus when needed."""
        with self._lock:
            project = self._require_project(project_id)
            now = _utc_now()
            updated = self._replace_fields(
                project,
                status=ProjectState.COMPLETED.value,
                progress=100.0,
                updated_at=now,
            )
            self._store_project(updated)
            if self._document.get("active_project_id") == updated.id:
                self._document["active_project_id"] = None
            self._save_document()
            logger.info(
                "PROJECT_COMPLETED id=%s name=%r",
                updated.id,
                updated.name,
            )

        self._notify_goal_active_project(updated, clear=True)
        self._sync_workspace_state()
        return updated

    def archive_project(self, project_id: str) -> Project:
        """Archive a project (retained, terminal)."""
        with self._lock:
            project = self._require_project(project_id)
            now = _utc_now()
            updated = self._replace_fields(
                project,
                status=ProjectState.ARCHIVED.value,
                updated_at=now,
            )
            self._store_project(updated)
            if self._document.get("active_project_id") == updated.id:
                self._document["active_project_id"] = None
            self._save_document()
            logger.info(
                "PROJECT_ARCHIVED id=%s name=%r",
                updated.id,
                updated.name,
            )

        self._notify_goal_active_project(updated, clear=True)
        self._sync_workspace_state()
        return updated

    def delete_project(self, project_id: str) -> None:
        """Permanently delete a project from persistence."""
        goal_id: str | None = None
        with self._lock:
            project = self._require_project(project_id)
            goal_id = project.goal_id
            projects = self._document.setdefault("projects", {})
            del projects[project_id]
            if self._document.get("active_project_id") == project_id:
                self._document["active_project_id"] = None
            self._save_document()
            logger.info("PROJECT_DELETED id=%s", project_id)

        if goal_id and self._goal_manager is not None:
            self._goal_manager.unregister_project(goal_id, project_id)
        self._sync_workspace_state()

    def has_project(self, project_id: str) -> bool:
        """Return True when the project id is owned by this manager."""
        with self._lock:
            return project_id in self._projects_map()

    def register_mission(
        self,
        project_id: str,
        mission_id: str,
        *,
        set_active: bool = False,
        mission_progress: float | None = None,
    ) -> Project:
        """Attach a mission id to a project (MissionManager ownership hook)."""
        with self._lock:
            project = self._require_project(project_id)
            mission_ids = list(project.mission_ids)
            if mission_id not in mission_ids:
                mission_ids.append(mission_id)
            kwargs: dict[str, Any] = {
                "mission_ids": mission_ids,
                "updated_at": _utc_now(),
            }
            if set_active:
                kwargs["active_mission_id"] = mission_id
            if mission_progress is not None:
                kwargs["progress"] = float(mission_progress)
            updated = self._replace_fields(project, **kwargs)
            self._store_project(updated)
            self._save_document()

        if set_active:
            self._notify_goal_active_project(updated, clear=False)
        elif mission_progress is not None:
            self._notify_goal_progress(updated)
        self._sync_workspace_state()
        return updated

    def unregister_mission(self, project_id: str, mission_id: str) -> Project | None:
        """Detach a mission id from a project when the mission is deleted."""
        with self._lock:
            project = self._projects_map().get(project_id)
            if project is None:
                return None
            mission_ids = [item for item in project.mission_ids if item != mission_id]
            active_mission_id = project.active_mission_id
            if active_mission_id == mission_id:
                active_mission_id = None
            updated = self._replace_fields(
                project,
                mission_ids=mission_ids,
                active_mission_id=active_mission_id,
                updated_at=_utc_now(),
            )
            self._store_project(updated)
            self._save_document()

        self._sync_workspace_state()
        return updated

    def set_active_mission(
        self,
        project_id: str,
        mission_id: str | None,
        *,
        progress: float | None = None,
    ) -> Project:
        """Update the project's active mission pointer (and optional progress)."""
        with self._lock:
            project = self._require_project(project_id)
            kwargs: dict[str, Any] = {
                "active_mission_id": mission_id,
                "updated_at": _utc_now(),
            }
            if progress is not None:
                kwargs["progress"] = float(progress)
            updated = self._replace_fields(project, **kwargs)
            self._store_project(updated)
            self._save_document()

        self._notify_goal_progress(updated)
        self._sync_workspace_state()
        return updated

    def update_progress(self, project_id: str, progress: float) -> Project:
        """Set stored project progress (0–100)."""
        with self._lock:
            project = self._require_project(project_id)
            updated = self._replace_fields(
                project,
                progress=max(0.0, min(100.0, float(progress))),
                updated_at=_utc_now(),
            )
            self._store_project(updated)
            self._save_document()

        self._notify_goal_progress(updated)
        self._sync_workspace_state()
        return updated

    def record_completed_mission(
        self,
        project_id: str,
        mission_id: str,
        *,
        mission_title: str | None = None,
    ) -> Project | None:
        """Append a completed mission id for project resume continuity (Phase 15.2)."""
        del mission_title  # Title resolved from WorkspaceState missions[] on sync.
        with self._lock:
            project = self._projects_map().get(project_id)
            if project is None:
                return None
            completed = list(project.completed_mission_ids)
            if mission_id not in completed:
                completed.append(mission_id)
            active_mission_id = project.active_mission_id
            if active_mission_id == mission_id:
                active_mission_id = None
            updated = self._replace_fields(
                project,
                completed_mission_ids=completed,
                active_mission_id=active_mission_id,
                updated_at=_utc_now(),
            )
            self._store_project(updated)
            self._save_document()

        # Phase 16.2 — mission completion refreshes owning goal progress.
        self._notify_goal_progress(updated)
        self._sync_workspace_state()
        return updated

    # ------------------------------------------------------------------
    # WorkspaceState mirror (ProjectManager owns truth)
    # ------------------------------------------------------------------

    def bind_state_manager(self, state_manager: StateManager | None) -> None:
        """Attach or replace the WorkspaceState mirror target."""
        self._state_manager = state_manager
        if self._state_manager is not None:
            self._sync_workspace_state()

    # ------------------------------------------------------------------
    # Phase 16.1 — goal ownership
    # ------------------------------------------------------------------

    def bind_goal_manager(self, goal_manager: GoalManager | None) -> None:
        """Attach or replace the GoalManager used for ownership validation."""
        self._goal_manager = goal_manager

    def _resolve_goal_id(self, goal_id: str | None) -> str | None:
        """Validate / default goal ownership when GoalManager is bound."""
        if self._goal_manager is None:
            return goal_id

        if goal_id is None:
            active = self._goal_manager.get_active_goal()
            if active is None:
                # Ensure every project has a goal without breaking Brain flows
                # that create projects before an explicit GoalManager create.
                default_name = "Titan"
                if self._state_manager is not None:
                    snap = self._state_manager.snapshot()
                    if snap.active_goal:
                        default_name = str(snap.active_goal)
                    elif snap.active_project:
                        default_name = str(snap.active_project)
                active = self._goal_manager.create_goal(default_name)
            goal_id = active.id

        self._validate_goal_ownership(goal_id)
        return goal_id

    def _validate_goal_ownership(self, goal_id: str) -> None:
        if self._goal_manager is None:
            return
        if not self._goal_manager.has_goal(goal_id):
            raise ValueError(
                f"Unknown goal id for project ownership: {goal_id}"
            )

    def _register_project_with_goal(self, project: Project) -> None:
        if self._goal_manager is None or not project.goal_id:
            return
        self._goal_manager.register_project(
            project.goal_id,
            project.id,
            set_active=project.status == ProjectState.ACTIVE.value,
            project_progress=float(project.progress),
        )

    def _notify_goal_active_project(
        self,
        project: Project,
        *,
        clear: bool,
    ) -> None:
        if self._goal_manager is None or not project.goal_id:
            return
        self._goal_manager.set_active_project(
            project.goal_id,
            None if clear else project.id,
            progress=float(project.progress),
        )

    def _notify_goal_progress(self, project: Project) -> None:
        """Refresh owning goal progress after a project/mission mutation (Phase 16.2)."""
        if self._goal_manager is None or not project.goal_id:
            return
        self._goal_manager.refresh_progress(project.goal_id)

    def _sync_workspace_state(self) -> None:
        """Mirror active project + concise project list into WorkspaceState.

        ProjectManager remains the owner of project truth. WorkspaceState stores
        ``projects[]`` and ``active_project_id`` so Brain can read once per turn
        from the single StateManager load — no duplicated project lookups.

        Phase 15.2 — also mirrors progress/resume structural fields (active mission,
        completed missions, last completed step, current objective). Summary and
        ``progress_updated_at`` are stamped by the think-cycle progress updater.
        """
        if self._state_manager is None:
            return

        logger.info("PROJECT_SYNC_BEGIN")
        snap = self._state_manager.snapshot()
        previous_id = snap.active_project_id
        active = self.get_active_project()
        all_projects = self.list_projects(include_archived=True)
        project_entries = [workspace_project_entry(item) for item in all_projects]

        if active is None:
            patch = {
                "active_project_id": None,
                "active_project_status": None,
                "active_project_progress": None,
                "active_project_active_mission": None,
                "active_project_completed_missions": [],
                "active_project_last_completed_step": None,
                "active_project_last_summary": None,
                "active_project_progress_updated_at": None,
                "active_project_current_objective": None,
                "projects": project_entries,
            }
            new_id: str | None = None
        else:
            mission_titles = {
                str(item.get("id")): str(item.get("title") or item.get("id"))
                for item in (snap.missions or [])
                if isinstance(item, dict) and item.get("id") is not None
            }
            completed_labels = [
                mission_titles.get(mid, mid) for mid in active.completed_mission_ids
            ]
            active_mission_label: str | None = None
            if active.active_mission_id:
                if (
                    snap.active_mission_id == active.active_mission_id
                    and (snap.active_mission_title or snap.active_mission)
                ):
                    active_mission_label = (
                        snap.active_mission_title or snap.active_mission
                    )
                else:
                    active_mission_label = mission_titles.get(
                        active.active_mission_id,
                        active.active_mission_id,
                    )

            # Structural resume from the mirrored active mission when it belongs
            # to this project; do not overwrite think-cycle summary stamps.
            last_completed = snap.active_project_last_completed_step
            objective = snap.active_project_current_objective
            if (
                active.active_mission_id
                and snap.active_mission_id == active.active_mission_id
            ):
                last_completed = snap.active_mission_last_completed_step
                objective = (
                    snap.active_mission_current_objective
                    or snap.active_mission_stage
                    or objective
                )

            patch = {
                "active_project_id": active.id,
                "active_project": active.name,
                "active_project_status": active.status,
                "active_project_progress": float(active.progress),
                "active_project_active_mission": active_mission_label,
                "active_project_completed_missions": completed_labels,
                "active_project_last_completed_step": last_completed,
                "active_project_current_objective": objective,
                "projects": project_entries,
            }
            new_id = active.id

        if previous_id != new_id:
            logger.info(
                "PROJECT_ACTIVE_CHANGED previous=%s new=%s",
                previous_id,
                new_id,
            )
            if previous_id is not None or new_id is not None:
                logger.info(
                    "PROJECT_SWITCHED previous=%s new=%s",
                    previous_id,
                    new_id,
                )
            # Project switch clears think-cycle resume stamps for the prior focus.
            if previous_id != new_id and new_id is not None and previous_id is not None:
                patch["active_project_last_summary"] = None
                patch["active_project_progress_updated_at"] = None

        self._state_manager.update(patch)
        logger.info(
            "PROJECT_SYNC_DONE active_id=%s count=%s",
            new_id,
            len(project_entries),
        )
        if active is not None:
            logger.info(
                "PROJECT_LOADED id=%s name=%r status=%s progress=%s",
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
        projects_raw = raw.get("projects", {})
        if not isinstance(projects_raw, dict):
            projects_raw = {}
        self._document = {
            "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
            "active_project_id": raw.get("active_project_id"),
            "projects": {
                str(key): value
                for key, value in projects_raw.items()
                if isinstance(value, dict)
            },
        }

    def _save_document(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "active_project_id": self._document.get("active_project_id"),
            "projects": dict(self._document.get("projects", {})),
        }
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

    def _projects_map(self) -> dict[str, Project]:
        raw = self._document.get("projects", {})
        result: dict[str, Project] = {}
        if not isinstance(raw, dict):
            return result
        for key, value in raw.items():
            if isinstance(value, dict):
                result[str(key)] = Project.from_dict(value)
        return result

    def _store_project(self, project: Project) -> None:
        projects = self._document.setdefault("projects", {})
        projects[project.id] = project.to_dict()

    def _require_project(self, project_id: str) -> Project:
        project = self._projects_map().get(project_id)
        if project is None:
            raise KeyError(f"Unknown project id: {project_id}")
        return project

    def _resolve_target(self, project_id: str | None) -> Project:
        if project_id is not None:
            return self._require_project(project_id)
        active = self.get_active_project()
        if active is None:
            raise ValueError("No active project to target")
        return active

    @staticmethod
    def _replace_fields(project: Project, **kwargs: Any) -> Project:
        data = project.to_dict()
        for key, value in kwargs.items():
            if key in {"created_at", "updated_at"} and isinstance(value, datetime):
                data[key] = value.isoformat()
            elif key == "priority" and isinstance(value, ProjectPriority):
                data[key] = value.value
            elif key in {
                "mission_ids",
                "completed_mission_ids",
                "aliases",
                "keywords",
            }:
                data[key] = list(value)
            else:
                data[key] = value
        return Project.from_dict(data)

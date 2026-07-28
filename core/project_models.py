# =====================================
# Titan Project Models
# =====================================

"""Structured project types for Phase 15.1 Project Manager foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class ProjectState(str, Enum):
    """Lifecycle states for a long-lived project.

    Only one project may be ``ACTIVE`` in the workspace at a time.
    """

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class ProjectPriority(str, Enum):
    """Relative priority for project attention."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_TERMINAL_PROJECT_STATES = frozenset({
    ProjectState.COMPLETED,
    ProjectState.ARCHIVED,
})


@dataclass
class Project:
    """Multi-mission project owned exclusively by ProjectManager.

    A project groups missions. Exactly one project may be ACTIVE at a time.
    Every mission belongs to exactly one project via ``Mission.project_id``.
    Every project belongs to exactly one goal via ``goal_id`` (Phase 16.1).
    """

    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    progress: float
    active_mission_id: str | None
    mission_ids: list[str]
    completed_mission_ids: list[str]
    priority: ProjectPriority
    # Phase 15.3 — matching signals for automatic project switching.
    aliases: list[str]
    keywords: list[str]
    # Phase 16.1 — owning goal (GoalManager validates ownership).
    goal_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status == ProjectState.ACTIVE.value

    @property
    def is_terminal(self) -> bool:
        try:
            return ProjectState(self.status) in _TERMINAL_PROJECT_STATES
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": round(float(self.progress), 2),
            "active_mission_id": self.active_mission_id,
            "mission_ids": list(self.mission_ids),
            "completed_mission_ids": list(self.completed_mission_ids),
            "priority": self.priority.value,
            "aliases": list(self.aliases),
            "keywords": list(self.keywords),
            "goal_id": self.goal_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        raw_status = data.get("status", ProjectState.ACTIVE.value)
        try:
            status = ProjectState(str(raw_status).upper()).value
        except ValueError:
            status = ProjectState.ACTIVE.value

        raw_priority = data.get("priority", ProjectPriority.NORMAL.value)
        try:
            priority = ProjectPriority(str(raw_priority).upper())
        except ValueError:
            priority = ProjectPriority.NORMAL

        mission_ids_raw = data.get("mission_ids", [])
        mission_ids = (
            [str(item) for item in mission_ids_raw]
            if isinstance(mission_ids_raw, list)
            else []
        )
        completed_raw = data.get("completed_mission_ids", [])
        completed_mission_ids = (
            [str(item) for item in completed_raw]
            if isinstance(completed_raw, list)
            else []
        )
        aliases = _string_list(data.get("aliases"))
        keywords = _string_list(data.get("keywords"))

        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            description=str(data.get("description", "") or ""),
            status=status,
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            progress=float(data.get("progress", 0.0) or 0.0),
            active_mission_id=(
                str(data["active_mission_id"])
                if data.get("active_mission_id") is not None
                else None
            ),
            mission_ids=mission_ids,
            completed_mission_ids=completed_mission_ids,
            priority=priority,
            aliases=aliases,
            keywords=keywords,
            goal_id=(
                str(data["goal_id"]) if data.get("goal_id") is not None else None
            ),
        )


def workspace_project_entry(project: Project) -> dict[str, Any]:
    """Concise WorkspaceState mirror entry (no full mission payloads)."""
    return {
        "id": project.id,
        "name": project.name,
        "status": project.status,
        "progress": float(project.progress),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            pass
    return datetime.now().astimezone()

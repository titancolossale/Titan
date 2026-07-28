# =====================================
# Titan Goal Models
# =====================================

"""Structured goal types for Phase 16.1–16.3 Goal Manager.

Distinct from ``core.mission_models.Goal`` (per-mission objective blob).
This module owns the workspace-level Goal entity that groups projects.

Phase 16.2 — ``GoalProgress`` is computed from every project contained in a goal.
Phase 16.3 — ``aliases`` / ``keywords`` support automatic goal matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class GoalState(str, Enum):
    """Lifecycle states for a long-lived goal.

    Only one goal may be ``ACTIVE`` in the workspace at a time.
    """

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class GoalPriority(str, Enum):
    """Relative priority for goal attention."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_TERMINAL_GOAL_STATES = frozenset({
    GoalState.COMPLETED,
    GoalState.ARCHIVED,
})


@dataclass
class Goal:
    """Multi-project goal owned exclusively by GoalManager.

    A goal groups projects. Exactly one goal may be ACTIVE at a time.
    Every project belongs to exactly one goal via ``Project.goal_id``.
    """

    id: str
    name: str
    description: str
    status: str
    priority: GoalPriority
    created_at: datetime
    updated_at: datetime
    progress: float
    project_ids: list[str]
    active_project_id: str | None
    # Phase 16.3 — matching signals for automatic goal switching.
    aliases: list[str]
    keywords: list[str]

    @property
    def is_active(self) -> bool:
        return self.status == GoalState.ACTIVE.value

    @property
    def is_terminal(self) -> bool:
        try:
            return GoalState(self.status) in _TERMINAL_GOAL_STATES
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": round(float(self.progress), 2),
            "project_ids": list(self.project_ids),
            "active_project_id": self.active_project_id,
            "aliases": list(self.aliases),
            "keywords": list(self.keywords),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goal:
        raw_status = data.get("status", GoalState.ACTIVE.value)
        try:
            status = GoalState(str(raw_status).upper()).value
        except ValueError:
            status = GoalState.ACTIVE.value

        raw_priority = data.get("priority", GoalPriority.NORMAL.value)
        try:
            priority = GoalPriority(str(raw_priority).upper())
        except ValueError:
            priority = GoalPriority.NORMAL

        project_ids_raw = data.get("project_ids", [])
        project_ids = (
            [str(item) for item in project_ids_raw]
            if isinstance(project_ids_raw, list)
            else []
        )

        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            description=str(data.get("description", "") or ""),
            status=status,
            priority=priority,
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            progress=float(data.get("progress", 0.0) or 0.0),
            project_ids=project_ids,
            active_project_id=(
                str(data["active_project_id"])
                if data.get("active_project_id") is not None
                else None
            ),
            aliases=_string_list(data.get("aliases")),
            keywords=_string_list(data.get("keywords")),
        )


@dataclass(frozen=True)
class GoalProgress:
    """Computed goal progress derived from contained projects (Phase 16.2).

    Produced by a single scan of the goal's ``project_ids`` — no duplicated
    project-registry walks.
    """

    progress: float
    completed_projects: int
    active_projects: int
    paused_projects: int
    total_projects: int
    last_activity: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "progress": round(float(self.progress), 2),
            "completed_projects": int(self.completed_projects),
            "active_projects": int(self.active_projects),
            "paused_projects": int(self.paused_projects),
            "total_projects": int(self.total_projects),
            "last_activity": (
                self.last_activity.isoformat() if self.last_activity is not None else None
            ),
        }


def compute_goal_progress_from_projects(
    projects: list[Any],
    *,
    fallback_activity: datetime | None = None,
) -> GoalProgress:
    """Derive GoalProgress from a pre-collected project list (single scan)."""
    total = len(projects)
    if total == 0:
        return GoalProgress(
            progress=0.0,
            completed_projects=0,
            active_projects=0,
            paused_projects=0,
            total_projects=0,
            last_activity=fallback_activity,
        )

    completed = 0
    active = 0
    paused = 0
    progress_sum = 0.0
    last_activity = fallback_activity

    for project in projects:
        status = str(getattr(project, "status", "") or "").upper()
        if status == "COMPLETED":
            completed += 1
        elif status == "ACTIVE":
            active += 1
        elif status == "PAUSED":
            paused += 1
        progress_sum += float(getattr(project, "progress", 0.0) or 0.0)
        updated = getattr(project, "updated_at", None)
        if isinstance(updated, datetime):
            if last_activity is None or updated > last_activity:
                last_activity = updated

    return GoalProgress(
        progress=round(progress_sum / float(total), 2),
        completed_projects=completed,
        active_projects=active,
        paused_projects=paused,
        total_projects=total,
        last_activity=last_activity,
    )


def workspace_goal_entry(goal: Goal) -> dict[str, Any]:
    """Concise WorkspaceState mirror entry (no full project payloads)."""
    return {
        "id": goal.id,
        "name": goal.name,
        "status": goal.status,
        "progress": float(goal.progress),
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

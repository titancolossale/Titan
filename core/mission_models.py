# =====================================
# Titan Mission Models
# =====================================

"""Structured mission types for Mission Runtime / Phase 14.1 Mission Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MissionState(str, Enum):
    """Lifecycle states for a long-running mission.

    Phase 14.5 workspace statuses (multi-mission):
    ``ACTIVE`` / ``QUEUED`` / ``PAUSED`` / ``COMPLETED`` / ``ARCHIVED``.
    Richer runtime states (PLANNING, READY, RUNNING, …) remain for execution.
    """

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    # Phase 14.5 — multi-mission workspace
    ACTIVE = "ACTIVE"
    QUEUED = "QUEUED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class MissionPriority(str, Enum):
    """Relative priority for mission scheduling attention."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskState(str, Enum):
    """State of an individual mission task (step)."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


_TERMINAL_MISSION_STATES = frozenset({
    MissionState.COMPLETED,
    MissionState.FAILED,
    MissionState.CANCELLED,
    MissionState.ARCHIVED,
})

# Focused / executable workspace missions (not queued, paused, or terminal).
_ACTIVE_MISSION_STATES = frozenset({
    MissionState.CREATED,
    MissionState.PLANNING,
    MissionState.READY,
    MissionState.RUNNING,
    MissionState.WAITING,
    MissionState.BLOCKED,
    MissionState.ACTIVE,
})

# Held in the workspace — retained, non-terminal, never the Brain focus.
_HELD_MISSION_STATES = frozenset({
    MissionState.QUEUED,
    MissionState.PAUSED,
})

_STARTED_MISSION_STATES = frozenset({
    MissionState.RUNNING,
    MissionState.ACTIVE,
    MissionState.WAITING,
    MissionState.BLOCKED,
})

# Phase 14.5 — canonical workspace statuses exposed to WorkspaceState / prompts.
WORKSPACE_MISSION_STATES = frozenset({
    MissionState.ACTIVE,
    MissionState.QUEUED,
    MissionState.PAUSED,
    MissionState.COMPLETED,
    MissionState.ARCHIVED,
})


@dataclass(frozen=True)
class Goal:
    """High-level objective attached to a mission."""

    description: str
    success_criteria: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "success_criteria": self.success_criteria,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Goal | None:
        if not data:
            return None
        return cls(
            description=str(data.get("description", "")),
            success_criteria=str(data.get("success_criteria", "")),
        )


@dataclass(frozen=True)
class Task:
    """One executable step within a mission."""

    id: str
    description: str
    order: int
    state: TaskState = TaskState.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "order": self.order,
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        raw_state = data.get("state", TaskState.PENDING.value)
        try:
            state = TaskState(str(raw_state))
        except ValueError:
            state = TaskState.PENDING
        return cls(
            id=str(data["id"]),
            description=str(data.get("description", "")),
            order=int(data.get("order", 0)),
            state=state,
        )


@dataclass(frozen=True)
class MissionHistoryEntry:
    """Append-only audit entry for mission lifecycle events."""

    event: str
    timestamp: datetime
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "timestamp": self.timestamp.isoformat(),
            "detail": self.detail,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionHistoryEntry:
        raw_ts = data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(str(raw_ts))
        except ValueError:
            timestamp = datetime.now().astimezone()
        metadata = data.get("metadata")
        return cls(
            event=str(data.get("event", "unknown")),
            timestamp=timestamp,
            detail=str(data.get("detail", "")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )


@dataclass(frozen=True)
class MissionProgress:
    """Computed progress snapshot for a mission."""

    mission_id: str
    state: MissionState
    current_step: str | None
    completed_count: int
    remaining_count: int
    total_steps: int
    progress_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "state": self.state.value,
            "current_step": self.current_step,
            "completed_count": self.completed_count,
            "remaining_count": self.remaining_count,
            "total_steps": self.total_steps,
            "progress_percent": round(self.progress_percent, 2),
        }


@dataclass
class Mission:
    """Current execution mission owned exclusively by MissionManager.

    Phase 14.1 foundation fields are first-class. Legacy Mission Runtime fields
    (``objective``, ``state``, ``progress_percent``, step lists, history) remain
    for Brain / pipeline compatibility and stay in sync with the foundation API.
    """

    id: str
    title: str
    description: str
    status: str
    priority: MissionPriority
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    progress: float
    tags: list[str]
    parent_mission: str | None
    child_missions: list[str]
    current_step: str | None
    next_step: str | None
    notes: str
    # Phase 15.1 — every mission belongs to exactly one project when owned.
    project_id: str | None
    # Legacy / runtime compatibility fields
    objective: str
    state: MissionState
    completed_steps: list[str]
    remaining_steps: list[str]
    progress_percent: float
    steps: list[str]
    history: list[MissionHistoryEntry]
    goal: Goal | None = None
    tasks: list[Task] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.state in _ACTIVE_MISSION_STATES

    @property
    def is_held(self) -> bool:
        """True when queued or paused (workspace-held, not Brain focus)."""
        return self.state in _HELD_MISSION_STATES

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_MISSION_STATES

    def workspace_status(self, *, is_focused: bool = False) -> str:
        """Return the Phase 14.5 workspace status label for this mission."""
        if self.state in {
            MissionState.QUEUED,
            MissionState.PAUSED,
            MissionState.COMPLETED,
            MissionState.ARCHIVED,
            MissionState.ACTIVE,
        }:
            return self.state.value
        if self.state in {MissionState.FAILED, MissionState.CANCELLED}:
            return self.state.value
        if is_focused and self.is_active:
            return MissionState.ACTIVE.value
        if self.is_active:
            return MissionState.QUEUED.value
        return self.state.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "progress": round(float(self.progress), 2),
            "tags": list(self.tags),
            "parent_mission": self.parent_mission,
            "child_missions": list(self.child_missions),
            "current_step": self.current_step,
            "next_step": self.next_step,
            "notes": self.notes,
            "project_id": self.project_id,
            # Legacy aliases kept in sync for Brain / schema consumers
            "objective": self.objective,
            "state": self.state.value,
            "completed_steps": list(self.completed_steps),
            "remaining_steps": list(self.remaining_steps),
            "progress_percent": round(float(self.progress_percent), 2),
            "steps": list(self.steps),
            "history": [entry.to_dict() for entry in self.history],
            "goal": self.goal.to_dict() if self.goal else None,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mission:
        raw_state = data.get("state") or data.get("status") or MissionState.CREATED.value
        try:
            state = MissionState(str(raw_state).upper())
        except ValueError:
            # Accept legacy lowercase status strings
            legacy = {
                "idle": MissionState.CREATED,
                "in_progress": MissionState.RUNNING,
                "completed": MissionState.COMPLETED,
                "cancelled": MissionState.CANCELLED,
                "failed": MissionState.FAILED,
                "archived": MissionState.ARCHIVED,
            }
            state = legacy.get(str(raw_state).lower(), MissionState.CREATED)

        raw_priority = data.get("priority", MissionPriority.NORMAL.value)
        try:
            priority = MissionPriority(str(raw_priority).upper())
        except ValueError:
            priority = MissionPriority.NORMAL

        history = [
            MissionHistoryEntry.from_dict(entry)
            for entry in data.get("history", [])
            if isinstance(entry, dict)
        ]
        tasks = [
            Task.from_dict(task)
            for task in data.get("tasks", [])
            if isinstance(task, dict)
        ]

        created_at = _parse_datetime(data.get("created_at"))
        updated_at = _parse_datetime(data.get("updated_at"))
        started_at = _parse_optional_datetime(data.get("started_at"))
        completed_at = _parse_optional_datetime(data.get("completed_at"))

        description = str(
            data.get("description")
            if data.get("description") is not None
            else data.get("objective", "")
        )
        objective = str(
            data.get("objective")
            if data.get("objective") is not None
            else description
        )
        if not description:
            description = objective
        if not objective:
            objective = description

        steps = list(data.get("steps", []))
        completed_steps = list(data.get("completed_steps", []))
        remaining_steps = list(data.get("remaining_steps", []))
        if not remaining_steps and steps:
            remaining_steps, _ = compute_progress(steps, completed_steps)

        progress_raw = data.get("progress", data.get("progress_percent", 0.0))
        progress = float(progress_raw or 0.0)
        progress_percent = float(data.get("progress_percent", progress) or 0.0)

        next_step = data.get("next_step")
        if next_step is None and remaining_steps:
            current = data.get("current_step")
            if current and current in remaining_steps:
                idx = remaining_steps.index(current)
                next_step = remaining_steps[idx + 1] if idx + 1 < len(remaining_steps) else None
            else:
                next_step = remaining_steps[0] if remaining_steps else None

        tags_raw = data.get("tags", [])
        tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
        children_raw = data.get("child_missions", [])
        child_missions = (
            [str(child) for child in children_raw]
            if isinstance(children_raw, list)
            else []
        )

        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            description=description,
            status=str(data.get("status") or state.value),
            priority=priority,
            created_at=created_at,
            updated_at=updated_at,
            started_at=started_at,
            completed_at=completed_at,
            progress=progress,
            tags=tags,
            parent_mission=(
                str(data["parent_mission"])
                if data.get("parent_mission") is not None
                else None
            ),
            child_missions=child_missions,
            current_step=data.get("current_step"),
            next_step=next_step if next_step is None else str(next_step),
            notes=str(data.get("notes", "") or ""),
            project_id=(
                str(data["project_id"])
                if data.get("project_id") is not None
                else None
            ),
            objective=objective,
            state=state,
            completed_steps=completed_steps,
            remaining_steps=remaining_steps,
            progress_percent=progress_percent,
            steps=steps,
            history=history,
            goal=Goal.from_dict(data.get("goal")),
            tasks=tasks,
        )


def compute_progress(
    steps: list[str],
    completed_steps: list[str],
) -> tuple[list[str], float]:
    """Return remaining steps and progress percent from step lists."""
    completed_set = set(completed_steps)
    remaining = [step for step in steps if step not in completed_set]
    total = len(steps)
    if total == 0:
        return remaining, 100.0 if completed_steps else 0.0
    percent = (len(completed_steps) / total) * 100.0
    return remaining, min(100.0, percent)


def build_mission_progress(mission: Mission) -> MissionProgress:
    """Build a MissionProgress snapshot from a Mission instance."""
    remaining, percent = compute_progress(mission.steps, mission.completed_steps)
    return MissionProgress(
        mission_id=mission.id,
        state=mission.state,
        current_step=mission.current_step,
        completed_count=len(mission.completed_steps),
        remaining_count=len(remaining),
        total_steps=len(mission.steps),
        progress_percent=percent,
    )


def resolve_next_step(
    steps: list[str],
    completed_steps: list[str],
    current_step: str | None,
) -> str | None:
    """Return the step after ``current_step``, or the first pending step."""
    remaining, _ = compute_progress(steps, completed_steps)
    if not remaining:
        return None
    if current_step and current_step in remaining:
        idx = remaining.index(current_step)
        if idx + 1 < len(remaining):
            return remaining[idx + 1]
        return None
    return remaining[0]


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            pass
    return datetime.now().astimezone()


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None

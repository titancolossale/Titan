# =====================================
# Titan Mission Models
# =====================================

"""Structured mission types for Mission Runtime V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MissionState(str, Enum):
    """Lifecycle states for a long-running mission."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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
})

_ACTIVE_MISSION_STATES = frozenset({
    MissionState.CREATED,
    MissionState.PLANNING,
    MissionState.READY,
    MissionState.RUNNING,
    MissionState.WAITING,
    MissionState.BLOCKED,
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
    """Long-running objective composed of tasks executed over time."""

    id: str
    title: str
    objective: str
    created_at: datetime
    updated_at: datetime
    state: MissionState
    priority: MissionPriority
    current_step: str | None
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
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL_MISSION_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "state": self.state.value,
            "priority": self.priority.value,
            "current_step": self.current_step,
            "completed_steps": list(self.completed_steps),
            "remaining_steps": list(self.remaining_steps),
            "progress_percent": round(self.progress_percent, 2),
            "steps": list(self.steps),
            "history": [entry.to_dict() for entry in self.history],
            "goal": self.goal.to_dict() if self.goal else None,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mission:
        raw_state = data.get("state", MissionState.CREATED.value)
        try:
            state = MissionState(str(raw_state))
        except ValueError:
            state = MissionState.CREATED

        raw_priority = data.get("priority", MissionPriority.NORMAL.value)
        try:
            priority = MissionPriority(str(raw_priority))
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

        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            objective=str(data.get("objective", "")),
            created_at=created_at,
            updated_at=updated_at,
            state=state,
            priority=priority,
            current_step=data.get("current_step"),
            completed_steps=list(data.get("completed_steps", [])),
            remaining_steps=list(data.get("remaining_steps", [])),
            progress_percent=float(data.get("progress_percent", 0.0)),
            steps=list(data.get("steps", [])),
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


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            pass
    return datetime.now().astimezone()

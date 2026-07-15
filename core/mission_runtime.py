# =====================================
# Titan Mission Runtime
# =====================================

"""Mission state management for long-running objectives (Mission Runtime V1).

Explicit execution only — no background workers, timers, or autonomous scheduling.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.mission_migrator import SCHEMA_VERSION, default_schema, migrate
from core.mission_models import (
    Goal,
    Mission,
    MissionHistoryEntry,
    MissionPriority,
    MissionProgress,
    MissionState,
    Task,
    TaskState,
    build_mission_progress,
    compute_progress,
)

logger = logging.getLogger(__name__)

_LEGACY_STATUS_TO_STATE = {
    "idle": None,
    "in_progress": MissionState.RUNNING,
    "completed": MissionState.COMPLETED,
    "cancelled": MissionState.CANCELLED,
    "inactive": None,
}

_STATE_TO_LEGACY_STATUS = {
    MissionState.CREATED: "in_progress",
    MissionState.PLANNING: "in_progress",
    MissionState.READY: "in_progress",
    MissionState.RUNNING: "in_progress",
    MissionState.WAITING: "in_progress",
    MissionState.BLOCKED: "in_progress",
    MissionState.COMPLETED: "completed",
    MissionState.FAILED: "failed",
    MissionState.CANCELLED: "cancelled",
}


class MissionRuntime:
    """Persist and manage multi-step missions across explicit execution turns."""

    def __init__(self, file_path: str | Path = "data/titan_mission.json") -> None:
        self.file_path = Path(file_path)
        self._document = self._load_document()

    def create_mission(
        self,
        title: str,
        objective: str,
        steps: list[str],
        *,
        priority: MissionPriority | str = MissionPriority.NORMAL,
        state: MissionState | str = MissionState.CREATED,
    ) -> Mission:
        """Create a new mission and set it as the active focus."""
        now = _utc_now()
        mission_id = str(uuid.uuid4())
        step_list = list(steps)
        tasks = _build_tasks(step_list)
        first_step = step_list[0] if step_list else None

        if isinstance(priority, str):
            priority = MissionPriority(priority)
        if isinstance(state, str):
            state = MissionState(state)

        runtime_state = state
        if runtime_state == MissionState.CREATED and step_list:
            runtime_state = MissionState.READY
        if runtime_state in {MissionState.READY, MissionState.RUNNING} and first_step:
            tasks[0] = Task(
                id=tasks[0].id,
                description=tasks[0].description,
                order=tasks[0].order,
                state=TaskState.IN_PROGRESS,
            )

        remaining, percent = compute_progress(step_list, [])
        history = [
            MissionHistoryEntry(
                event="mission_created",
                timestamp=now,
                detail=f"Mission « {title} » created with {len(step_list)} step(s).",
            )
        ]

        mission = Mission(
            id=mission_id,
            title=title,
            objective=objective,
            created_at=now,
            updated_at=now,
            state=runtime_state,
            priority=priority,
            current_step=first_step,
            completed_steps=[],
            remaining_steps=remaining,
            progress_percent=percent,
            steps=step_list,
            history=history,
            goal=Goal(description=objective),
            tasks=tasks,
        )

        missions = self._document.setdefault("missions", {})
        missions[mission_id] = mission.to_dict()
        self._document["active_mission_id"] = mission_id
        self._sync_legacy_view()
        self._save_document()

        logger.info(
            "Mission created id=%s title=%r state=%s steps=%s",
            mission_id,
            title,
            runtime_state.value,
            len(step_list),
        )
        return mission

    def resume_mission(self, mission_id: str) -> Mission:
        """Resume a paused or waiting mission and set it as active."""
        mission = self._require_mission(mission_id)
        if mission.state in {
            MissionState.COMPLETED,
            MissionState.CANCELLED,
            MissionState.FAILED,
        }:
            raise ValueError(
                f"Cannot resume mission {mission_id} in terminal state {mission.state.value}",
            )

        now = _utc_now()
        updated = _replace_mission_fields(
            mission,
            state=MissionState.RUNNING,
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_resumed",
                    timestamp=now,
                    detail=f"Mission « {mission.title} » resumed.",
                )
            ],
        )
        self._store_mission(updated)
        self._document["active_mission_id"] = mission_id
        self._sync_legacy_view()
        self._save_document()

        logger.info("Mission resumed id=%s title=%r", mission_id, mission.title)
        return updated

    def update_mission(
        self,
        mission_id: str,
        *,
        title: str | None = None,
        objective: str | None = None,
        state: MissionState | str | None = None,
        priority: MissionPriority | str | None = None,
        current_step: str | None = None,
        steps: list[str] | None = None,
    ) -> Mission:
        """Update mission fields and append a history entry."""
        mission = self._require_mission(mission_id)
        now = _utc_now()
        changes: list[str] = []

        new_title = title if title is not None else mission.title
        new_objective = objective if objective is not None else mission.objective
        new_steps = list(steps) if steps is not None else list(mission.steps)
        new_completed = list(mission.completed_steps)

        if isinstance(state, str):
            state = MissionState(state)
        new_state = state if state is not None else mission.state

        if isinstance(priority, str):
            priority = MissionPriority(priority)
        new_priority = priority if priority is not None else mission.priority

        new_current = current_step if current_step is not None else mission.current_step
        if steps is not None:
            new_current = _resolve_current_step(new_steps, new_completed, new_current)
            changes.append("steps")

        if title is not None and title != mission.title:
            changes.append("title")
        if objective is not None and objective != mission.objective:
            changes.append("objective")
        if state is not None and state != mission.state:
            changes.append("state")
        if priority is not None and priority != mission.priority:
            changes.append("priority")

        remaining, percent = compute_progress(new_steps, new_completed)
        new_tasks = _sync_tasks(new_steps, new_completed, new_current)

        updated = _replace_mission_fields(
            mission,
            title=new_title,
            objective=new_objective,
            state=new_state,
            priority=new_priority,
            current_step=new_current,
            steps=new_steps,
            completed_steps=new_completed,
            remaining_steps=remaining,
            progress_percent=percent,
            tasks=new_tasks,
            goal=Goal(description=new_objective),
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_updated",
                    timestamp=now,
                    detail=f"Updated fields: {', '.join(changes) or 'metadata'}.",
                    metadata={"changed": changes},
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission_id:
            self._sync_legacy_view()
        self._save_document()

        logger.info(
            "Mission updated id=%s changes=%s state=%s",
            mission_id,
            changes or ["metadata"],
            new_state.value,
        )
        return updated

    def complete_mission(self, mission_id: str) -> Mission:
        """Mark a mission as completed."""
        mission = self._require_mission(mission_id)
        now = _utc_now()
        all_steps = list(mission.steps)
        updated = _replace_mission_fields(
            mission,
            state=MissionState.COMPLETED,
            current_step=None,
            completed_steps=all_steps,
            remaining_steps=[],
            progress_percent=100.0,
            tasks=_mark_all_tasks(all_steps, TaskState.COMPLETED),
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_completed",
                    timestamp=now,
                    detail=f"Mission « {mission.title} » marked completed.",
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission_id:
            self._sync_legacy_view()
        self._save_document()

        logger.info("Mission completed id=%s title=%r", mission_id, mission.title)
        return updated

    def fail_mission(self, mission_id: str, *, reason: str = "") -> Mission:
        """Mark a mission as failed."""
        mission = self._require_mission(mission_id)
        now = _utc_now()
        updated = _replace_mission_fields(
            mission,
            state=MissionState.FAILED,
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_failed",
                    timestamp=now,
                    detail=reason or f"Mission « {mission.title} » failed.",
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission_id:
            self._sync_legacy_view()
        self._save_document()

        logger.info("Mission failed id=%s reason=%r", mission_id, reason)
        return updated

    def list_active_missions(self) -> list[Mission]:
        """Return missions that are not in a terminal state."""
        missions = self._document.get("missions", {})
        result: list[Mission] = []
        for raw in missions.values():
            if not isinstance(raw, dict):
                continue
            mission = Mission.from_dict(raw)
            if mission.is_active:
                result.append(mission)
        result.sort(key=lambda item: item.updated_at, reverse=True)
        return result

    def get_mission(self, mission_id: str) -> Mission | None:
        """Return a mission by id, or None when missing."""
        raw = self._document.get("missions", {}).get(mission_id)
        if not isinstance(raw, dict):
            return None
        return Mission.from_dict(raw)

    def get_active_mission(self) -> Mission | None:
        """Return the focused mission when it is in a non-terminal state."""
        active_id = self._document.get("active_mission_id")
        if not active_id:
            return None
        mission = self.get_mission(str(active_id))
        if mission is None or not mission.is_active:
            return None
        return mission

    def get_focused_mission(self) -> Mission | None:
        """Return the mission referenced by active_mission_id regardless of state."""
        active_id = self._document.get("active_mission_id")
        if not active_id:
            return None
        return self.get_mission(str(active_id))

    def get_progress(self, mission_id: str) -> MissionProgress:
        """Return a computed progress snapshot for a mission."""
        mission = self._require_mission(mission_id)
        return build_mission_progress(mission)

    def complete_current_step(self, mission_id: str | None = None) -> Mission | None:
        """Advance the mission by recording the current step in history."""
        mission = self._resolve_target_mission(mission_id)
        if mission is None:
            return None

        current = mission.current_step
        if not current:
            return mission

        completed = list(mission.completed_steps)
        if current not in completed:
            completed.append(current)

        next_step = _next_pending_step(mission.steps, completed)
        now = _utc_now()
        remaining, percent = compute_progress(mission.steps, completed)
        new_state = MissionState.COMPLETED if next_step is None else mission.state
        if next_step is None:
            new_state = MissionState.COMPLETED

        updated = _replace_mission_fields(
            mission,
            completed_steps=completed,
            current_step=next_step,
            remaining_steps=remaining,
            progress_percent=percent,
            state=new_state,
            tasks=_sync_tasks(mission.steps, completed, next_step),
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="step_completed",
                    timestamp=now,
                    detail=f"Step completed: « {current} ».",
                    metadata={"step": current, "next_step": next_step},
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission.id:
            if updated.state == MissionState.COMPLETED:
                updated = _replace_mission_fields(
                    updated,
                    history=updated.history + [
                        MissionHistoryEntry(
                            event="mission_completed",
                            timestamp=now,
                            detail=f"Mission « {updated.title} » completed.",
                        )
                    ],
                )
                self._store_mission(updated)
                logger.info("Mission completed id=%s title=%r", mission.id, mission.title)
            self._sync_legacy_view()
        self._save_document()
        return updated

    def on_tool_execution_complete(
        self,
        *,
        success: bool,
        summary_message: str,
        completed_tool_steps: int = 0,
        failed_tool_steps: int = 0,
        mission_id: str | None = None,
    ) -> Mission | None:
        """Update mission progress after Tool Execution Engine finishes."""
        mission = self._resolve_target_mission(mission_id)
        if mission is None:
            return None
        if mission.state not in {
            MissionState.RUNNING,
            MissionState.READY,
            MissionState.WAITING,
            MissionState.PLANNING,
        }:
            return mission

        now = _utc_now()
        event = "tool_execution_completed" if success else "tool_execution_failed"
        detail = summary_message or (
            "Tool execution completed." if success else "Tool execution failed."
        )
        metadata = {
            "success": success,
            "completed_tool_steps": completed_tool_steps,
            "failed_tool_steps": failed_tool_steps,
        }

        new_state = mission.state
        if not success and failed_tool_steps > 0:
            new_state = MissionState.BLOCKED
        elif success and mission.state == MissionState.READY:
            new_state = MissionState.RUNNING

        remaining, percent = compute_progress(mission.steps, mission.completed_steps)
        updated = _replace_mission_fields(
            mission,
            state=new_state,
            remaining_steps=remaining,
            progress_percent=percent,
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event=event,
                    timestamp=now,
                    detail=detail[:500],
                    metadata=metadata,
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission.id:
            self._sync_legacy_view()
        self._save_document()

        logger.info(
            "Mission tool execution recorded id=%s success=%s progress=%.1f%%",
            mission.id,
            success,
            percent,
        )
        return updated

    def cancel_mission(self, mission_id: str | None = None) -> Mission | None:
        """Cancel an active mission without deleting history."""
        mission = self._resolve_target_mission(mission_id)
        if mission is None:
            return None

        now = _utc_now()
        updated = _replace_mission_fields(
            mission,
            state=MissionState.CANCELLED,
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_cancelled",
                    timestamp=now,
                    detail=f"Mission « {mission.title} » cancelled.",
                )
            ],
        )
        self._store_mission(updated)
        if self._document.get("active_mission_id") == mission.id:
            self._sync_legacy_view()
        self._save_document()

        logger.info("Mission cancelled id=%s title=%r", mission.id, mission.title)
        return updated

    def get_legacy_mission_view(self) -> dict[str, Any]:
        """Return v2-compatible single-mission dict for Brain pipeline."""
        return copy.deepcopy(self._legacy_view())

    def get_document(self) -> dict[str, Any]:
        """Return the full persisted mission document."""
        return copy.deepcopy(self._document)

    def _load_document(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return default_schema()

        with self.file_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        return migrate(raw)

    def _save_document(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(self._document, file, indent=4, ensure_ascii=False)

    def _require_mission(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if mission is None:
            raise KeyError(f"Mission not found: {mission_id}")
        return mission

    def _resolve_target_mission(self, mission_id: str | None) -> Mission | None:
        if mission_id:
            return self.get_mission(mission_id)
        return self.get_active_mission()

    def _store_mission(self, mission: Mission) -> None:
        missions = self._document.setdefault("missions", {})
        missions[mission.id] = mission.to_dict()

    def _sync_legacy_view(self) -> None:
        legacy = self._legacy_view()
        for key, value in legacy.items():
            if key in {"missions", "active_mission_id"}:
                continue
            self._document[key] = value

    def _legacy_view(self) -> dict[str, Any]:
        """Build v2 flat mission dict from focused runtime mission."""
        focused = self.get_focused_mission()
        base = {
            "schema_version": SCHEMA_VERSION,
            "active_mission_id": self._document.get("active_mission_id"),
            "missions": copy.deepcopy(self._document.get("missions", {})),
            "active": False,
            "title": None,
            "objective": None,
            "steps": [],
            "completed_steps": [],
            "current_step": None,
            "status": "idle",
        }
        if focused is None:
            return base

        legacy_status = _STATE_TO_LEGACY_STATUS.get(focused.state, "in_progress")
        base.update({
            "active": focused.is_active,
            "title": focused.title,
            "objective": focused.objective,
            "steps": list(focused.steps),
            "completed_steps": list(focused.completed_steps),
            "current_step": focused.current_step,
            "status": legacy_status,
        })
        return base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_tasks(steps: list[str]) -> list[Task]:
    return [
        Task(
            id=str(uuid.uuid4()),
            description=step,
            order=index,
            state=TaskState.PENDING,
        )
        for index, step in enumerate(steps)
    ]


def _sync_tasks(
    steps: list[str],
    completed_steps: list[str],
    current_step: str | None,
) -> list[Task]:
    completed_set = set(completed_steps)
    tasks: list[Task] = []
    for index, step in enumerate(steps):
        if step in completed_set:
            state = TaskState.COMPLETED
        elif step == current_step:
            state = TaskState.IN_PROGRESS
        else:
            state = TaskState.PENDING
        tasks.append(
            Task(
                id=str(uuid.uuid4()),
                description=step,
                order=index,
                state=state,
            )
        )
    return tasks


def _mark_all_tasks(steps: list[str], state: TaskState) -> list[Task]:
    return [
        Task(
            id=str(uuid.uuid4()),
            description=step,
            order=index,
            state=state,
        )
        for index, step in enumerate(steps)
    ]


def _next_pending_step(steps: list[str], completed_steps: list[str]) -> str | None:
    completed_set = set(completed_steps)
    for step in steps:
        if step not in completed_set:
            return step
    return None


def _resolve_current_step(
    steps: list[str],
    completed_steps: list[str],
    current_step: str | None,
) -> str | None:
    if current_step and current_step in steps:
        return current_step
    return _next_pending_step(steps, completed_steps)


def _replace_mission_fields(mission: Mission, **kwargs: Any) -> Mission:
    data = mission.to_dict()
    for key, value in kwargs.items():
        if key == "history":
            data["history"] = [entry.to_dict() for entry in value]
        elif key == "tasks":
            data["tasks"] = [task.to_dict() for task in value]
        elif key == "goal" and value is not None:
            data["goal"] = value.to_dict()
        elif key in {"created_at", "updated_at"} and isinstance(value, datetime):
            data[key] = value.isoformat()
        elif key == "state" and isinstance(value, MissionState):
            data["state"] = value.value
        elif key == "priority" and isinstance(value, MissionPriority):
            data["priority"] = value.value
        else:
            data[key] = value
    return Mission.from_dict(data)

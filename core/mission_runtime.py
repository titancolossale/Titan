# =====================================
# Titan Mission Runtime
# =====================================

"""Mission state management for long-running objectives (Mission Runtime V1).

Explicit execution only — no background workers, timers, or autonomous scheduling.
Phase 14.1 adds thread-safe ownership, hierarchy, archive/delete, and foundation fields.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
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
    resolve_next_step,
)

logger = logging.getLogger(__name__)

_LEGACY_STATUS_TO_STATE = {
    "idle": None,
    "in_progress": MissionState.RUNNING,
    "completed": MissionState.COMPLETED,
    "cancelled": MissionState.CANCELLED,
    "inactive": None,
    "archived": MissionState.ARCHIVED,
}

_STATE_TO_LEGACY_STATUS = {
    MissionState.CREATED: "in_progress",
    MissionState.PLANNING: "in_progress",
    MissionState.READY: "in_progress",
    MissionState.RUNNING: "in_progress",
    MissionState.WAITING: "in_progress",
    MissionState.BLOCKED: "in_progress",
    MissionState.ACTIVE: "in_progress",
    MissionState.QUEUED: "inactive",
    MissionState.PAUSED: "inactive",
    MissionState.COMPLETED: "completed",
    MissionState.FAILED: "failed",
    MissionState.CANCELLED: "cancelled",
    MissionState.ARCHIVED: "archived",
}


class MissionRuntime:
    """Persist and manage multi-step missions across explicit execution turns.

    Thread-safe single owner of the mission document. External callers must go
    through ``MissionManager`` / these methods — never mutate mission JSON directly.
    """

    def __init__(self, file_path: str | Path = "data/titan_mission.json") -> None:
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._document = self._load_document()

    def create_mission(
        self,
        title: str,
        objective: str = "",
        steps: list[str] | None = None,
        *,
        description: str | None = None,
        priority: MissionPriority | str = MissionPriority.NORMAL,
        state: MissionState | str = MissionState.CREATED,
        tags: list[str] | None = None,
        parent_mission: str | None = None,
        notes: str = "",
        current_step: str | None = None,
        project_id: str | None = None,
    ) -> Mission:
        """Create a new mission and set it as the active focus."""
        with self._lock:
            now = _utc_now()
            mission_id = str(uuid.uuid4())
            step_list = list(steps or [])
            tasks = _build_tasks(step_list)
            first_step = current_step if current_step in step_list else (
                step_list[0] if step_list else None
            )
            desc = description if description is not None else objective
            obj = objective or desc

            if isinstance(priority, str):
                priority = MissionPriority(priority.strip().upper())
            if isinstance(state, str):
                state = MissionState(state.strip().upper())

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

            if parent_mission is not None:
                self._require_mission(parent_mission)

            remaining, percent = compute_progress(step_list, [])
            next_step = resolve_next_step(step_list, [], first_step)
            started_at = now if runtime_state == MissionState.RUNNING else None
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
                description=desc,
                status=runtime_state.value,
                priority=priority,
                created_at=now,
                updated_at=now,
                started_at=started_at,
                completed_at=None,
                progress=percent,
                tags=list(tags or []),
                parent_mission=parent_mission,
                child_missions=[],
                current_step=first_step,
                next_step=next_step,
                notes=notes or "",
                project_id=project_id,
                objective=obj,
                state=runtime_state,
                completed_steps=[],
                remaining_steps=remaining,
                progress_percent=percent,
                steps=step_list,
                history=history,
                goal=Goal(description=desc or obj),
                tasks=tasks,
            )

            # Phase 14.5 — only one ACTIVE mission; demote the previous focus to QUEUED.
            previous_active_id = self._document.get("active_mission_id")
            if previous_active_id and previous_active_id != mission_id:
                self._queue_mission_unlocked(str(previous_active_id), now)

            missions = self._document.setdefault("missions", {})
            missions[mission_id] = mission.to_dict()
            self._document["active_mission_id"] = mission_id

            if parent_mission is not None:
                parent = self._require_mission(parent_mission)
                children = list(parent.child_missions)
                if mission_id not in children:
                    children.append(mission_id)
                parent_updated = _replace_mission_fields(
                    parent,
                    child_missions=children,
                    updated_at=now,
                )
                self._store_mission(parent_updated)

            self._sync_legacy_view()
            self._save_document()

            logger.info(
                "MISSION_CREATED id=%s title=%r state=%s steps=%s",
                mission_id,
                title,
                runtime_state.value,
                len(step_list),
            )
            if previous_active_id and previous_active_id != mission_id:
                logger.info(
                    "MISSION_SWITCHED previous=%s new=%s",
                    previous_active_id,
                    mission_id,
                )
            return mission

    def resume_mission(self, mission_id: str) -> Mission:
        """Resume a paused or queued mission and set it as the ACTIVE focus."""
        with self._lock:
            mission = self._require_mission(mission_id)
            if mission.is_terminal:
                raise ValueError(
                    f"Cannot resume mission {mission_id} in terminal state "
                    f"{mission.state.value}",
                )

            now = _utc_now()
            previous_active_id = self._document.get("active_mission_id")
            if previous_active_id and previous_active_id != mission_id:
                self._queue_mission_unlocked(str(previous_active_id), now)

            updated = _replace_mission_fields(
                mission,
                state=MissionState.RUNNING,
                status=MissionState.RUNNING.value,
                started_at=mission.started_at or now,
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

            logger.info(
                "MISSION_RESUMED id=%s title=%r",
                mission_id,
                mission.title,
            )
            if previous_active_id and previous_active_id != mission_id:
                logger.info(
                    "MISSION_SWITCHED previous=%s new=%s",
                    previous_active_id,
                    mission_id,
                )
            return updated

    def pause_mission(self, mission_id: str | None = None) -> Mission:
        """Pause a mission (Phase 14.5). Clears ACTIVE focus when pausing the focus."""
        with self._lock:
            mission = self._resolve_target_mission(mission_id)
            if mission is None:
                raise ValueError("No mission available to pause.")
            if mission.is_terminal:
                raise ValueError(
                    f"Cannot pause mission {mission.id} in terminal state "
                    f"{mission.state.value}",
                )

            now = _utc_now()
            updated = _replace_mission_fields(
                mission,
                state=MissionState.PAUSED,
                status=MissionState.PAUSED.value,
                updated_at=now,
                history=mission.history + [
                    MissionHistoryEntry(
                        event="mission_paused",
                        timestamp=now,
                        detail=f"Mission « {mission.title} » paused.",
                    )
                ],
            )
            self._store_mission(updated)
            if self._document.get("active_mission_id") == mission.id:
                self._document["active_mission_id"] = None
            self._sync_legacy_view()
            self._save_document()

            logger.info("MISSION_PAUSED id=%s title=%r", mission.id, mission.title)
            return updated

    def update_mission(
        self,
        mission_id: str,
        *,
        title: str | None = None,
        objective: str | None = None,
        description: str | None = None,
        state: MissionState | str | None = None,
        status: str | MissionState | None = None,
        priority: MissionPriority | str | None = None,
        current_step: str | None = None,
        next_step: str | None = None,
        steps: list[str] | None = None,
        progress: float | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
        parent_mission: str | None = None,
    ) -> Mission:
        """Update mission fields and append a history entry."""
        with self._lock:
            mission = self._require_mission(mission_id)
            now = _utc_now()
            changes: list[str] = []

            new_title = title if title is not None else mission.title
            if description is not None:
                new_description = description
                new_objective = objective if objective is not None else description
            elif objective is not None:
                new_description = objective
                new_objective = objective
            else:
                new_description = mission.description
                new_objective = mission.objective

            new_steps = list(steps) if steps is not None else list(mission.steps)
            new_completed = list(mission.completed_steps)

            resolved_state = state
            if resolved_state is None and status is not None:
                resolved_state = status
            if isinstance(resolved_state, MissionState):
                new_state = resolved_state
            elif isinstance(resolved_state, str):
                new_state = MissionState(resolved_state.strip().upper())
            else:
                new_state = mission.state

            if isinstance(priority, MissionPriority):
                new_priority = priority
            elif isinstance(priority, str):
                new_priority = MissionPriority(priority.strip().upper())
            else:
                new_priority = mission.priority

            new_current = current_step if current_step is not None else mission.current_step
            if steps is not None:
                new_current = _resolve_current_step(new_steps, new_completed, new_current)
                changes.append("steps")

            if title is not None and title != mission.title:
                changes.append("title")
            if new_description != mission.description or new_objective != mission.objective:
                changes.append("description")
            if resolved_state is not None and resolved_state != mission.state:
                changes.append("status")
            if priority is not None and priority != mission.priority:
                changes.append("priority")
            if tags is not None:
                changes.append("tags")
            if notes is not None:
                changes.append("notes")
            if parent_mission is not None and parent_mission != mission.parent_mission:
                changes.append("parent_mission")

            remaining, computed_percent = compute_progress(new_steps, new_completed)
            new_percent = (
                float(progress) if progress is not None else computed_percent
            )
            new_next = (
                next_step
                if next_step is not None
                else resolve_next_step(new_steps, new_completed, new_current)
            )
            new_tasks = _sync_tasks(new_steps, new_completed, new_current)

            started_at = mission.started_at
            completed_at = mission.completed_at
            if new_state == MissionState.RUNNING and started_at is None:
                started_at = now
            if new_state == MissionState.ACTIVE and started_at is None:
                started_at = now
            if new_state in {
                MissionState.COMPLETED,
                MissionState.CANCELLED,
                MissionState.FAILED,
                MissionState.ARCHIVED,
            }:
                completed_at = completed_at or now
                if new_state == MissionState.COMPLETED:
                    new_percent = 100.0

            new_parent = (
                parent_mission if parent_mission is not None else mission.parent_mission
            )
            if parent_mission is not None and parent_mission != mission.parent_mission:
                if parent_mission:
                    self._require_mission(parent_mission)
                self._unlink_child(mission.parent_mission, mission_id)
                if parent_mission:
                    self._link_child(parent_mission, mission_id, now)

            updated = _replace_mission_fields(
                mission,
                title=new_title,
                description=new_description,
                objective=new_objective,
                state=new_state,
                status=new_state.value,
                priority=new_priority,
                current_step=new_current,
                next_step=new_next,
                steps=new_steps,
                completed_steps=new_completed,
                remaining_steps=remaining,
                progress=new_percent,
                progress_percent=new_percent,
                tags=list(tags) if tags is not None else list(mission.tags),
                notes=notes if notes is not None else mission.notes,
                parent_mission=new_parent,
                started_at=started_at,
                completed_at=completed_at,
                tasks=new_tasks,
                goal=Goal(description=new_description or new_objective),
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
        with self._lock:
            mission = self._require_mission(mission_id)
            now = _utc_now()
            all_steps = list(mission.steps)
            updated = _replace_mission_fields(
                mission,
                state=MissionState.COMPLETED,
                status=MissionState.COMPLETED.value,
                current_step=None,
                next_step=None,
                completed_steps=all_steps,
                remaining_steps=[],
                progress=100.0,
                progress_percent=100.0,
                started_at=mission.started_at or now,
                completed_at=now,
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

            logger.info(
                "MISSION_COMPLETED id=%s title=%r",
                mission_id,
                mission.title,
            )
            return updated

    def fail_mission(self, mission_id: str, *, reason: str = "") -> Mission:
        """Mark a mission as failed."""
        with self._lock:
            mission = self._require_mission(mission_id)
            now = _utc_now()
            updated = _replace_mission_fields(
                mission,
                state=MissionState.FAILED,
                status=MissionState.FAILED.value,
                completed_at=now,
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

    def archive_mission(self, mission_id: str) -> Mission:
        """Archive a mission (terminal, retained in the document)."""
        with self._lock:
            mission = self._require_mission(mission_id)
            now = _utc_now()
            updated = _replace_mission_fields(
                mission,
                state=MissionState.ARCHIVED,
                status=MissionState.ARCHIVED.value,
                completed_at=mission.completed_at or now,
                updated_at=now,
                history=mission.history + [
                    MissionHistoryEntry(
                        event="mission_archived",
                        timestamp=now,
                        detail=f"Mission « {mission.title} » archived.",
                    )
                ],
            )
            self._store_mission(updated)
            if self._document.get("active_mission_id") == mission_id:
                self._sync_legacy_view()
            self._save_document()

            logger.info(
                "MISSION_ARCHIVED id=%s title=%r",
                mission_id,
                mission.title,
            )
            return updated

    def delete_mission(self, mission_id: str) -> None:
        """Permanently remove a mission from the document."""
        with self._lock:
            mission = self._require_mission(mission_id)
            self._unlink_child(mission.parent_mission, mission_id)

            # Detach children rather than cascading deletes.
            for child_id in list(mission.child_missions):
                child = self.get_mission(child_id)
                if child is not None:
                    self._store_mission(
                        _replace_mission_fields(
                            child,
                            parent_mission=None,
                            updated_at=_utc_now(),
                        )
                    )

            missions = self._document.setdefault("missions", {})
            missions.pop(mission_id, None)
            if self._document.get("active_mission_id") == mission_id:
                self._document["active_mission_id"] = None
            self._sync_legacy_view()
            self._save_document()

            logger.info("Mission deleted id=%s title=%r", mission_id, mission.title)

    def list_missions(
        self,
        *,
        status: str | MissionState | None = None,
        include_archived: bool = True,
        active_only: bool = False,
    ) -> list[Mission]:
        """Return missions, optionally filtered by status / activity.

        ``active_only`` means non-terminal (includes QUEUED / PAUSED workspace
        holds). The single Brain focus remains ``get_active_mission()``.
        """
        with self._lock:
            status_filter: MissionState | None = None
            if isinstance(status, MissionState):
                status_filter = status
            elif isinstance(status, str) and status.strip():
                status_filter = MissionState(status.strip().upper())

            result: list[Mission] = []
            for raw in self._document.get("missions", {}).values():
                if not isinstance(raw, dict):
                    continue
                mission = Mission.from_dict(raw)
                if active_only and mission.is_terminal:
                    continue
                if not include_archived and mission.state == MissionState.ARCHIVED:
                    continue
                if status_filter is not None and mission.state != status_filter:
                    continue
                result.append(mission)
            result.sort(key=lambda item: item.updated_at, reverse=True)
            return result

    def list_active_missions(self) -> list[Mission]:
        """Return missions that are not in a terminal state (incl. queued/paused)."""
        return self.list_missions(active_only=True, include_archived=False)

    def get_mission(self, mission_id: str) -> Mission | None:
        """Return a mission by id, or None when missing."""
        with self._lock:
            raw = self._document.get("missions", {}).get(mission_id)
            if not isinstance(raw, dict):
                return None
            return Mission.from_dict(raw)

    def get_active_mission(self) -> Mission | None:
        """Return the focused mission when it is the ACTIVE workspace focus.

        Queued / paused / terminal missions are never returned — Brain reasons
        only against the single ACTIVE mission.
        """
        with self._lock:
            active_id = self._document.get("active_mission_id")
            if not active_id:
                return None
            mission = self.get_mission(str(active_id))
            if mission is None or mission.is_terminal or mission.is_held:
                return None
            if not mission.is_active:
                return None
            return mission

    def get_focused_mission(self) -> Mission | None:
        """Return the mission referenced by active_mission_id regardless of state."""
        with self._lock:
            active_id = self._document.get("active_mission_id")
            if not active_id:
                return None
            return self.get_mission(str(active_id))

    def get_progress(self, mission_id: str) -> MissionProgress:
        """Return a computed progress snapshot for a mission."""
        with self._lock:
            mission = self._require_mission(mission_id)
            return build_mission_progress(mission)

    def complete_current_step(self, mission_id: str | None = None) -> Mission | None:
        """Advance the mission by recording the current step in history."""
        with self._lock:
            mission = self._resolve_target_mission(mission_id)
            if mission is None:
                return None

            current = mission.current_step
            if not current:
                return mission

            completed = list(mission.completed_steps)
            if current not in completed:
                completed.append(current)

            next_pending = _next_pending_step(mission.steps, completed)
            now = _utc_now()
            remaining, percent = compute_progress(mission.steps, completed)
            new_state = (
                MissionState.COMPLETED if next_pending is None else mission.state
            )
            next_step = resolve_next_step(mission.steps, completed, next_pending)

            updated = _replace_mission_fields(
                mission,
                completed_steps=completed,
                current_step=next_pending,
                next_step=next_step,
                remaining_steps=remaining,
                progress=percent,
                progress_percent=percent,
                state=new_state,
                status=new_state.value,
                started_at=mission.started_at or now,
                completed_at=now if new_state == MissionState.COMPLETED else mission.completed_at,
                tasks=_sync_tasks(mission.steps, completed, next_pending),
                updated_at=now,
                history=mission.history + [
                    MissionHistoryEntry(
                        event="step_completed",
                        timestamp=now,
                        detail=f"Step completed: « {current} ».",
                        metadata={"step": current, "next_step": next_pending},
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
                    logger.info(
                        "MISSION_COMPLETED id=%s title=%r",
                        mission.id,
                        mission.title,
                    )
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
        with self._lock:
            mission = self._resolve_target_mission(mission_id)
            if mission is None:
                return None
            if mission.state not in {
                MissionState.RUNNING,
                MissionState.ACTIVE,
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
            elif success and mission.state in {
                MissionState.READY,
                MissionState.ACTIVE,
            }:
                new_state = MissionState.RUNNING

            remaining, percent = compute_progress(mission.steps, mission.completed_steps)
            updated = _replace_mission_fields(
                mission,
                state=new_state,
                status=new_state.value,
                remaining_steps=remaining,
                progress=percent,
                progress_percent=percent,
                started_at=mission.started_at or (
                    now if new_state == MissionState.RUNNING else mission.started_at
                ),
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
        with self._lock:
            mission = self._resolve_target_mission(mission_id)
            if mission is None:
                return None

            now = _utc_now()
            updated = _replace_mission_fields(
                mission,
                state=MissionState.CANCELLED,
                status=MissionState.CANCELLED.value,
                completed_at=now,
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
        with self._lock:
            return copy.deepcopy(self._legacy_view())

    def get_document(self) -> dict[str, Any]:
        """Return the full persisted mission document."""
        with self._lock:
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

    def _link_child(self, parent_id: str, child_id: str, now: datetime) -> None:
        parent = self._require_mission(parent_id)
        children = list(parent.child_missions)
        if child_id not in children:
            children.append(child_id)
            self._store_mission(
                _replace_mission_fields(
                    parent,
                    child_missions=children,
                    updated_at=now,
                )
            )

    def _unlink_child(self, parent_id: str | None, child_id: str) -> None:
        if not parent_id:
            return
        parent = self.get_mission(parent_id)
        if parent is None:
            return
        children = [item for item in parent.child_missions if item != child_id]
        if children != parent.child_missions:
            self._store_mission(
                _replace_mission_fields(
                    parent,
                    child_missions=children,
                    updated_at=_utc_now(),
                )
            )

    def _queue_mission_unlocked(self, mission_id: str, now: datetime) -> None:
        """Demote a displaced focus candidate to QUEUED (caller holds lock).

        Preserves PAUSED / BLOCKED / terminal states — only active working
        states become QUEUED when another mission takes the ACTIVE focus.
        """
        mission = self.get_mission(mission_id)
        if mission is None or mission.is_terminal:
            return
        if mission.state in {
            MissionState.QUEUED,
            MissionState.PAUSED,
            MissionState.BLOCKED,
        }:
            return
        if mission.state not in {
            MissionState.CREATED,
            MissionState.PLANNING,
            MissionState.READY,
            MissionState.RUNNING,
            MissionState.ACTIVE,
            MissionState.WAITING,
        }:
            return
        queued = _replace_mission_fields(
            mission,
            state=MissionState.QUEUED,
            status=MissionState.QUEUED.value,
            updated_at=now,
            history=mission.history + [
                MissionHistoryEntry(
                    event="mission_queued",
                    timestamp=now,
                    detail=(
                        f"Mission « {mission.title} » queued "
                        "(another mission is ACTIVE)."
                    ),
                )
            ],
        )
        self._store_mission(queued)

    def _sync_legacy_view(self) -> None:
        legacy = self._legacy_view()
        for key, value in legacy.items():
            if key in {"missions", "active_mission_id"}:
                continue
            self._document[key] = value

    def _legacy_view(self) -> dict[str, Any]:
        """Build v2 flat mission dict from focused runtime mission.

        Phase 14.5 — never embed the full ``missions`` map in the Brain-facing
        view (empty placeholder only). Queued / paused / archived mission
        *bodies* must not pollute prompts; WorkspaceState carries concise counts.
        """
        focused = self.get_focused_mission()
        base = {
            "schema_version": SCHEMA_VERSION,
            "active_mission_id": self._document.get("active_mission_id"),
            "missions": {},
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
            "id": focused.id,
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
        elif key in {"created_at", "updated_at", "started_at", "completed_at"}:
            if value is None:
                data[key] = None
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            else:
                data[key] = value
        elif key == "state" and isinstance(value, MissionState):
            data["state"] = value.value
            data["status"] = value.value
        elif key == "priority" and isinstance(value, MissionPriority):
            data["priority"] = value.value
        elif key == "tags":
            data["tags"] = list(value)
        elif key == "child_missions":
            data["child_missions"] = list(value)
        else:
            data[key] = value

    # Keep foundation aliases synchronized.
    if "description" in kwargs and "objective" not in kwargs:
        data["objective"] = data["description"]
    if "objective" in kwargs and "description" not in kwargs:
        data["description"] = data["objective"]
    if "progress" in kwargs and "progress_percent" not in kwargs:
        data["progress_percent"] = data["progress"]
    if "progress_percent" in kwargs and "progress" not in kwargs:
        data["progress"] = data["progress_percent"]
    if "state" in kwargs and "status" not in kwargs:
        data["status"] = data["state"]
    if "status" in kwargs and "state" not in kwargs:
        data["state"] = str(data["status"]).upper()

    return Mission.from_dict(data)

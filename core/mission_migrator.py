# =====================================
# Titan Mission Migrator
# =====================================

"""Schema migration for mission JSON (Phase 8 / Phase 14.1 Mission Manager)."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = 4

_MISSION_FOUNDATION_DEFAULTS = {
    "description": "",
    "status": "CREATED",
    "started_at": None,
    "completed_at": None,
    "progress": 0.0,
    "tags": [],
    "parent_mission": None,
    "child_missions": [],
    "next_step": None,
    "notes": "",
}


def default_schema() -> dict:
    """Return the canonical mission document (schema v4)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "active_mission_id": None,
        "missions": {},
        "active": False,
        "title": None,
        "objective": None,
        "steps": [],
        "completed_steps": [],
        "current_step": None,
        "status": "idle",
    }


def migrate(data: dict) -> dict:
    """Upgrade legacy mission documents to schema v4."""
    version = data.get("schema_version")
    if version == SCHEMA_VERSION:
        return _ensure_v4_fields(data)
    if version == 3:
        return _ensure_v4_fields(_migrate_v3_to_v4(data))
    if version == 2:
        return _ensure_v4_fields(_migrate_v3_to_v4(_migrate_v2_to_v3(data)))
    return _ensure_v4_fields(_migrate_v3_to_v4(_migrate_v1_to_v3(data)))


def _migrate_v1_to_v3(data: dict) -> dict:
    """Upgrade legacy v1/v2 flat mission to v3."""
    migrated = copy.deepcopy(data)
    migrated["schema_version"] = 2
    migrated.setdefault("completed_steps", [])

    if migrated.get("current_step") and migrated["current_step"] not in migrated["steps"]:
        current = migrated["current_step"]
        if current not in migrated["completed_steps"]:
            migrated["steps"] = [current] + list(migrated.get("steps", []))

    if migrated.get("status") == "inactive":
        migrated["status"] = "idle"

    return _migrate_v2_to_v3(migrated)


def _migrate_v2_to_v3(data: dict) -> dict:
    """Wrap a v2 single-mission document into v3 missions map."""
    migrated = copy.deepcopy(data)
    migrated["schema_version"] = 3
    migrated.setdefault("completed_steps", [])

    if not migrated.get("active") or not migrated.get("title"):
        migrated["active_mission_id"] = None
        migrated["missions"] = migrated.get("missions", {})
        return migrated

    mission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    status = migrated.get("status", "in_progress")
    state = _legacy_status_to_state(status)
    steps = list(migrated.get("steps", []))
    completed = list(migrated.get("completed_steps", []))
    remaining = [step for step in steps if step not in set(completed)]
    total = len(steps)
    percent = (len(completed) / total * 100.0) if total else 0.0
    objective = migrated.get("objective") or ""

    migrated["missions"] = {
        mission_id: {
            "id": mission_id,
            "title": migrated.get("title"),
            "description": objective,
            "objective": objective,
            "created_at": now,
            "updated_at": now,
            "started_at": now if state == "RUNNING" else None,
            "completed_at": now if state in {"COMPLETED", "CANCELLED", "FAILED"} else None,
            "state": state,
            "status": state,
            "priority": "NORMAL",
            "current_step": migrated.get("current_step"),
            "next_step": remaining[1] if len(remaining) > 1 else None,
            "completed_steps": completed,
            "remaining_steps": remaining,
            "progress": round(percent, 2),
            "progress_percent": round(percent, 2),
            "steps": steps,
            "tags": [],
            "parent_mission": None,
            "child_missions": [],
            "notes": "",
            "history": [
                {
                    "event": "migrated_from_v2",
                    "timestamp": now,
                    "detail": "Mission imported from schema v2.",
                }
            ],
            "goal": {
                "description": objective,
                "success_criteria": "",
            },
            "tasks": [],
        }
    }
    migrated["active_mission_id"] = mission_id
    return migrated


def _migrate_v3_to_v4(data: dict) -> dict:
    """Add Phase 14.1 foundation fields to each mission record."""
    migrated = copy.deepcopy(data)
    migrated["schema_version"] = SCHEMA_VERSION
    missions = migrated.get("missions")
    if not isinstance(missions, dict):
        migrated["missions"] = {}
        return migrated

    for mission_id, raw in list(missions.items()):
        if not isinstance(raw, dict):
            continue
        missions[mission_id] = _ensure_mission_foundation_fields(raw)
    return migrated


def _legacy_status_to_state(status: str) -> str:
    mapping = {
        "idle": "CREATED",
        "in_progress": "RUNNING",
        "completed": "COMPLETED",
        "cancelled": "CANCELLED",
        "failed": "FAILED",
        "archived": "ARCHIVED",
    }
    return mapping.get(str(status), "RUNNING")


def _ensure_mission_foundation_fields(raw: dict) -> dict:
    """Guarantee Phase 14.1 fields exist on a single mission record."""
    mission = copy.deepcopy(raw)
    objective = str(mission.get("objective") or mission.get("description") or "")
    state = str(mission.get("state") or mission.get("status") or "CREATED")
    progress = float(
        mission.get("progress", mission.get("progress_percent", 0.0)) or 0.0
    )

    mission.setdefault("description", objective)
    mission.setdefault("objective", objective or mission.get("description", ""))
    mission.setdefault("state", state)
    mission.setdefault("status", state)
    mission.setdefault("started_at", None)
    mission.setdefault("completed_at", None)
    mission.setdefault("progress", round(progress, 2))
    mission.setdefault("progress_percent", round(progress, 2))
    mission.setdefault("tags", [])
    mission.setdefault("parent_mission", None)
    mission.setdefault("child_missions", [])
    mission.setdefault("notes", "")
    mission.setdefault("next_step", None)
    mission.setdefault("completed_steps", [])
    mission.setdefault("remaining_steps", [])
    mission.setdefault("steps", [])
    mission.setdefault("history", [])
    mission.setdefault("tasks", [])

    if not isinstance(mission.get("tags"), list):
        mission["tags"] = []
    if not isinstance(mission.get("child_missions"), list):
        mission["child_missions"] = []
    if mission.get("notes") is None:
        mission["notes"] = ""

    remaining = mission.get("remaining_steps") or []
    current = mission.get("current_step")
    if mission.get("next_step") is None and remaining:
        if current and current in remaining:
            idx = remaining.index(current)
            mission["next_step"] = (
                remaining[idx + 1] if idx + 1 < len(remaining) else None
            )
        else:
            mission["next_step"] = remaining[0]

    return mission


def _ensure_v4_fields(data: dict) -> dict:
    """Guarantee all document + per-mission foundation keys exist."""
    result = copy.deepcopy(data)
    defaults = default_schema()
    for key, value in defaults.items():
        result.setdefault(key, value)
    result["schema_version"] = SCHEMA_VERSION
    if not isinstance(result.get("completed_steps"), list):
        result["completed_steps"] = []
    if not isinstance(result.get("steps"), list):
        result["steps"] = []
    if not isinstance(result.get("missions"), dict):
        result["missions"] = {}

    missions = result["missions"]
    for mission_id, raw in list(missions.items()):
        if isinstance(raw, dict):
            missions[mission_id] = _ensure_mission_foundation_fields(raw)
    return result

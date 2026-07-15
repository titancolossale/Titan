# =====================================
# Titan Mission Migrator
# =====================================

"""Schema migration for mission JSON (Phase 8 — P8-001, Mission Runtime V1)."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = 3


def default_schema() -> dict:
    """Return the canonical v3 mission document."""
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
    """Upgrade legacy mission documents to schema v3."""
    version = data.get("schema_version")
    if version == SCHEMA_VERSION:
        return _ensure_v3_fields(data)
    if version == 2:
        return _ensure_v3_fields(_migrate_v2_to_v3(data))
    return _ensure_v3_fields(_migrate_v1_to_v3(data))


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
    migrated["schema_version"] = SCHEMA_VERSION
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

    migrated["missions"] = {
        mission_id: {
            "id": mission_id,
            "title": migrated.get("title"),
            "objective": migrated.get("objective"),
            "created_at": now,
            "updated_at": now,
            "state": state,
            "priority": "NORMAL",
            "current_step": migrated.get("current_step"),
            "completed_steps": completed,
            "remaining_steps": remaining,
            "progress_percent": round(percent, 2),
            "steps": steps,
            "history": [
                {
                    "event": "migrated_from_v2",
                    "timestamp": now,
                    "detail": "Mission imported from schema v2.",
                }
            ],
            "goal": {
                "description": migrated.get("objective") or "",
                "success_criteria": "",
            },
            "tasks": [],
        }
    }
    migrated["active_mission_id"] = mission_id
    return migrated


def _legacy_status_to_state(status: str) -> str:
    mapping = {
        "idle": "CREATED",
        "in_progress": "RUNNING",
        "completed": "COMPLETED",
        "cancelled": "CANCELLED",
        "failed": "FAILED",
    }
    return mapping.get(str(status), "RUNNING")


def _ensure_v3_fields(data: dict) -> dict:
    """Guarantee all v3 keys exist without mutating unrelated fields."""
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
    return result

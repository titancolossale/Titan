# =====================================
# Titan Mission Migrator
# =====================================

"""Schema migration for mission JSON (Phase 8 — P8-001)."""

from __future__ import annotations

import copy

SCHEMA_VERSION = 2


def default_schema() -> dict:
    """Return the canonical v2 mission document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "active": False,
        "title": None,
        "objective": None,
        "steps": [],
        "completed_steps": [],
        "current_step": None,
        "status": "idle",
    }


def migrate(data: dict) -> dict:
    """Upgrade legacy mission documents to schema v2."""
    if data.get("schema_version") == SCHEMA_VERSION:
        return _ensure_v2_fields(data)

    migrated = copy.deepcopy(data)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated.setdefault("completed_steps", [])

    if migrated.get("current_step") and migrated["current_step"] not in migrated["steps"]:
        current = migrated["current_step"]
        if current not in migrated["completed_steps"]:
            migrated["steps"] = [current] + list(migrated.get("steps", []))

    if migrated.get("status") == "inactive":
        migrated["status"] = "idle"

    return _ensure_v2_fields(migrated)


def _ensure_v2_fields(data: dict) -> dict:
    """Guarantee all v2 keys exist without mutating unrelated fields."""
    result = copy.deepcopy(data)
    defaults = default_schema()
    for key, value in defaults.items():
        result.setdefault(key, value)
    result["schema_version"] = SCHEMA_VERSION
    if not isinstance(result.get("completed_steps"), list):
        result["completed_steps"] = []
    if not isinstance(result.get("steps"), list):
        result["steps"] = []
    return result

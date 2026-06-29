# =====================================
# Titan Memory Migrator
# =====================================

"""Schema migration for long-term memory JSON (Phase 3 — P3-002)."""

from __future__ import annotations

import copy
import re

SCHEMA_VERSION = 2

_CATEGORY_PREFIX_RE = re.compile(
    r"^\[(goals|preferences|projects|notes)\]\s*",
    re.IGNORECASE,
)


def default_schema() -> dict:
    """Return the canonical v1 long-term memory document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "users": {
            "Nolan": {
                "role": "Créateur de Titan",
                "authority": "principal",
                "goals": [],
                "preferences": [],
                "active_projects": ["Titan"],
                "projects": [],
                "notes": [],
                "project_namespaces": {},
            },
            "Ibrahim": {
                "role": "Utilisateur principal de Titan",
                "authority": "égal à Nolan",
                "goals": [],
                "preferences": [],
                "active_projects": [],
                "projects": [],
                "notes": [],
                "project_namespaces": {},
            },
        },
        "titan": {
            "mission": (
                "Aider Nolan et Ibrahim à construire, organiser, "
                "automatiser et améliorer leurs projets."
            ),
            "current_project": "Titan",
            "current_phase": "Développement du système de mémoire permanente",
        },
    }


def migrate(data: dict) -> dict:
    """Upgrade legacy memory documents to current schema in place (returns new dict)."""
    version = data.get("schema_version", 0)
    if version >= SCHEMA_VERSION:
        return _ensure_user_arrays(data)

    migrated = copy.deepcopy(data)
    if version < 1:
        migrated["schema_version"] = 1
        users = migrated.setdefault("users", {})
        for user_name, user_data in list(users.items()):
            users[user_name] = _migrate_user(user_data)
        if "titan" not in migrated:
            migrated["titan"] = default_schema()["titan"]

    if migrated.get("schema_version", 0) < 2:
        migrated = _migrate_v2_project_namespaces(migrated)

    migrated["schema_version"] = SCHEMA_VERSION
    return migrated


def _migrate_v2_project_namespaces(data: dict) -> dict:
    """Add project_namespaces to each user block (P9-030)."""
    result = copy.deepcopy(data)
    users = result.setdefault("users", {})
    for user_name, user_data in users.items():
        user = copy.deepcopy(user_data)
        user.setdefault("project_namespaces", {})
        users[user_name] = user
    return result


def _migrate_user(user_data: dict) -> dict:
    """Normalize a single user block to v1 categorized arrays."""
    user = copy.deepcopy(user_data)
    already_v1 = "active_projects" in user

    goals = list(user.pop("goals", []))
    preferences = list(user.pop("preferences", []))
    project_memories = list(user.pop("projects", []))
    notes = list(user.pop("notes", []))

    active_projects: list[str] = []
    if already_v1:
        active_projects = list(user.pop("active_projects", []))
    elif project_memories and all(
        isinstance(item, str) and not _CATEGORY_PREFIX_RE.match(item)
        for item in project_memories
    ):
        active_projects = [str(item) for item in project_memories]
        project_memories = []

    categorized_preferences: list[str] = []
    categorized_projects: list[str] = []
    categorized_notes: list[str] = []
    categorized_goals: list[str] = []

    for item in preferences:
        text = str(item)
        if _CATEGORY_PREFIX_RE.match(text):
            categorized_notes.append(text)
        else:
            categorized_preferences.append(text)

    for item in notes:
        text = str(item)
        match = _CATEGORY_PREFIX_RE.match(text)
        if not match:
            categorized_notes.append(text)
            continue
        category = match.group(1).lower()
        content = text[match.end():].strip()
        if not content:
            continue
        if category == "goals":
            categorized_goals.append(content)
        elif category == "preferences":
            categorized_preferences.append(content)
        elif category == "projects":
            categorized_projects.append(content)
        else:
            categorized_notes.append(content)

    user["goals"] = goals + categorized_goals
    user["preferences"] = categorized_preferences
    user["active_projects"] = active_projects
    user["projects"] = project_memories + categorized_projects
    user["notes"] = categorized_notes
    user.setdefault("project_namespaces", {})

    for key in ("goals", "preferences", "active_projects", "projects", "notes"):
        user.setdefault(key, [])

    return user


def _ensure_user_arrays(data: dict) -> dict:
    """Ensure v1 documents still have all required user keys."""
    result = copy.deepcopy(data)
    users = result.setdefault("users", {})
    for user_name, user_data in users.items():
        users[user_name] = _migrate_user(user_data)
    return result

# =====================================
# Titan Memory Migrator Tests
# =====================================

"""Regression tests for long-term memory schema migration (P3-003 / P3-004)."""

from __future__ import annotations

from memory.memory_migrator import SCHEMA_VERSION, default_schema, migrate


LEGACY_FIXTURE: dict = {
    "users": {
        "Nolan": {
            "role": "Créateur de Titan",
            "authority": "principal",
            "preferences": [],
            "projects": ["Titan"],
            "notes": [
                "Je préfère travailler la nuit.",
                "[projects] salut titan",
                "[preferences] j'aime Python",
                "[goals] apprendre le trading",
            ],
        },
        "Ibrahim": {
            "role": "Utilisateur principal de Titan",
            "authority": "égal à Nolan",
            "preferences": [],
            "projects": [],
        },
    },
    "titan": {
        "mission": "Mission test",
        "current_project": "Titan",
        "current_phase": "Test",
    },
}


def test_default_schema_has_version_and_category_arrays() -> None:
    """P3-001: default schema must include schema_version and typed arrays."""
    schema = default_schema()

    assert schema["schema_version"] == SCHEMA_VERSION
    assert "goals" in schema["users"]["Nolan"]
    assert "active_projects" in schema["users"]["Nolan"]
    assert "projects" in schema["users"]["Nolan"]


def test_migrate_legacy_moves_project_names_to_active_projects() -> None:
    """P3-002: legacy projects list becomes active_projects, not memory items."""
    result = migrate(LEGACY_FIXTURE)

    nolan = result["users"]["Nolan"]
    assert nolan["active_projects"] == ["Titan"]
    assert result["schema_version"] == SCHEMA_VERSION


def test_migrate_legacy_splits_prefixed_notes_into_categories() -> None:
    """P3-002: [category] prefixed notes migrate into typed arrays."""
    result = migrate(LEGACY_FIXTURE)
    nolan = result["users"]["Nolan"]

    assert "salut titan" in nolan["projects"]
    assert "j'aime Python" in nolan["preferences"]
    assert "apprendre le trading" in nolan["goals"]
    assert "Je préfère travailler la nuit." in nolan["notes"]


def test_migrate_is_idempotent() -> None:
    """P3-003: running migrate twice must not duplicate or corrupt data."""
    once = migrate(LEGACY_FIXTURE)
    twice = migrate(once)

    assert twice == once


def test_migrate_preserves_titan_block() -> None:
    """P3-002: titan metadata survives migration."""
    result = migrate(LEGACY_FIXTURE)

    assert result["titan"]["mission"] == "Mission test"


def test_migrate_ensures_ibrahim_category_arrays() -> None:
    """P3-002: users missing notes/goals get empty arrays."""
    result = migrate(LEGACY_FIXTURE)
    ibrahim = result["users"]["Ibrahim"]

    assert ibrahim["goals"] == []
    assert ibrahim["notes"] == []
    assert ibrahim["active_projects"] == []

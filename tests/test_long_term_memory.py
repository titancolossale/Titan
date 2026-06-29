# =====================================
# Titan LongTermMemory Tests
# =====================================

"""Persistence tests for LongTermMemory with schema migration (P3-003)."""

from __future__ import annotations

import json
from pathlib import Path

from memory.long_term_memory import LongTermMemory


def test_load_missing_file_returns_default_schema(tmp_path: Path) -> None:
    """Missing file must yield v1 default schema."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")

    memory = ltm.get_memory()
    assert memory["schema_version"] == 2
    assert "Nolan" in memory["users"]


def test_load_legacy_file_migrates_on_load(tmp_path: Path) -> None:
    """Legacy JSON without schema_version is migrated and saved on load."""
    path = tmp_path / "long_term_memory.json"
    legacy = {
        "users": {
            "Nolan": {
                "role": "Créateur",
                "authority": "principal",
                "preferences": [],
                "projects": ["Titan"],
                "notes": ["[goals] viser l'excellence"],
            }
        },
        "titan": {"mission": "Test"},
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    ltm = LongTermMemory(file_path=path)
    memory = ltm.get_memory()

    assert memory["schema_version"] == 2
    assert "viser l'excellence" in memory["users"]["Nolan"]["goals"]

    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["schema_version"] == 2


def test_write_categorized_stores_in_typed_array(tmp_path: Path) -> None:
    """P3-012: write_categorized appends to the correct user array."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")

    ltm.write_categorized("Nolan", "preferences", "Préfère le café")

    memory = ltm.get_memory()
    assert "Préfère le café" in memory["users"]["Nolan"]["preferences"]


def test_forget_matching_removes_items(tmp_path: Path) -> None:
    """P3-030 prep: forget_matching removes items containing query."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")
    ltm.write_categorized("Nolan", "notes", "Secret trading alpha")
    ltm.write_categorized("Nolan", "notes", "Autre note")

    removed = ltm.forget_matching("Nolan", "trading")

    assert removed == 1
    notes = ltm.get_memory()["users"]["Nolan"]["notes"]
    assert "Secret trading alpha" not in notes
    assert "Autre note" in notes

# =====================================
# Titan Project Memory Tests
# =====================================

"""Tests for Phase 9 project memory namespaces (P9-030)."""

from __future__ import annotations

from pathlib import Path

from memory.long_term_memory import LongTermMemory
from memory.memory_retriever import MemoryRetriever
from memory.memory_service import MemoryService
from memory.memory_manager import MemoryManager
from memory.project_memory import ProjectMemoryStore


def test_project_namespace_isolated_per_user(tmp_path: Path) -> None:
    """Nolan and Ibrahim project memory must not mix."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")
    store = ProjectMemoryStore(ltm.get_memory())

    store.write_note("Nolan", "Titan", "Architecture Phase 9")
    store.write_note("Ibrahim", "Titan", "Trading bot setup")
    ltm.save_memory()

    nolan_text = store.format_namespace("Nolan", "Titan")
    ibrahim_text = store.format_namespace("Ibrahim", "Titan")

    assert "Phase 9" in nolan_text
    assert "Trading bot" in ibrahim_text
    assert "Trading bot" not in nolan_text


def test_retriever_includes_project_namespace(tmp_path: Path) -> None:
    """Project-scoped items appear when project_id is provided."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")
    store = ProjectMemoryStore(ltm.get_memory())
    store.write_note("Nolan", "AlphaProject", "Utiliser pytest pour les tests")
    ltm.save_memory()

    retriever = MemoryRetriever()
    result = retriever.retrieve_for_user(
        ltm.get_memory(),
        "parle-moi des tests pytest",
        user="Nolan",
        project_id="AlphaProject",
    )

    assert result.has_matches
    assert "pytest" in result.text.lower()


def test_memory_service_project_write(tmp_path: Path) -> None:
    """MemoryService.write_project_note persists via facade."""
    service = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    service.write_project_note("Nolan", "Beta", "Checkpoint hebdomadaire")

    text = service.get_project_memory_text("Nolan", "Beta")
    assert "Checkpoint hebdomadaire" in text


def test_migration_adds_project_namespaces(tmp_path: Path) -> None:
    """v1 documents upgrade to schema v2 with project_namespaces."""
    ltm = LongTermMemory(file_path=tmp_path / "long_term_memory.json")
    doc = ltm.get_memory()

    assert doc.get("schema_version") == 2
    assert "project_namespaces" in doc["users"]["Nolan"]

# =====================================
# Titan Memory Service Tests
# =====================================

"""Tests for unified MemoryService API (P3-010–P3-013)."""

from __future__ import annotations

from pathlib import Path

from memory.long_term_memory import LongTermMemory
from memory.memory_decider import MemoryDecider
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService


def _service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )


def test_retrieve_filters_by_user(tmp_path: Path) -> None:
    """P3-022: retrieval scoped to user must not leak other users' data."""
    service = _service(tmp_path)
    doc = service.get_document()
    doc["users"]["Nolan"]["notes"] = ["Secret Nolan trading"]
    doc["users"]["Ibrahim"]["notes"] = ["Secret Ibrahim hobby"]
    service.long_term.memory = doc

    result = service.retrieve("Nolan", "parle-moi de trading")

    assert "Secret Nolan trading" in result.text
    assert "Ibrahim" not in result.text


def test_maybe_remember_writes_to_correct_category(tmp_path: Path) -> None:
    """P3-012: classified writes land in typed arrays."""
    service = _service(tmp_path)

    saved = service.maybe_remember("Nolan", "Mon objectif est d'apprendre Rust")

    assert saved is True
    memory = service.get_document()
    assert "Mon objectif est d'apprendre Rust" in memory["users"]["Nolan"]["goals"]


def test_maybe_remember_attributes_ibrahim_from_message(tmp_path: Path) -> None:
    """P3-020: messages mentioning Ibrahim store under Ibrahim profile."""
    service = _service(tmp_path)

    service.maybe_remember("Nolan", "Ibrahim dit : je préfère le thé vert")

    memory = service.get_document()
    assert "Ibrahim dit : je préfère le thé vert" in memory["users"]["Ibrahim"]["preferences"]


def test_salut_titan_does_not_auto_save(tmp_path: Path) -> None:
    """P3-021: casual greeting must not trigger memory write."""
    service = _service(tmp_path)

    saved = service.maybe_remember("Nolan", "salut titan")

    assert saved is False
    assert service.get_document()["users"]["Nolan"]["notes"] == []


def test_remember_session_delegates_to_short_term(tmp_path: Path) -> None:
    """P3-013: session notes stay in short-term store."""
    manager = MemoryManager()
    service = MemoryService(
        short_term=manager,
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )

    service.remember_session("Note session")

    assert "Note session" in manager.memory.short_term

# =====================================
# Titan Memory Facade Tests
# =====================================

"""Smoke tests for MemoryFacade delegation (P1-120 / P1-122)."""

from __future__ import annotations

from pathlib import Path

from memory.long_term_memory import LongTermMemory
from memory.memory_facade import MemoryFacade
from memory.memory_manager import MemoryManager


def test_remember_session_delegates_to_short_term_memory() -> None:
    """P1-122: remember_session must append to MemoryManager short-term store."""
    manager = MemoryManager()
    facade = MemoryFacade(short_term=manager, long_term=LongTermMemory())

    facade.remember_session("Note de session test")

    assert "Note de session test" in manager.memory.short_term


def test_get_long_term_delegates_to_long_term_memory(tmp_path: Path) -> None:
    """P1-122: get_long_term must return LongTermMemory document."""
    long_term = LongTermMemory(file_path=tmp_path / "long_term_memory.json")
    facade = MemoryFacade(short_term=MemoryManager(), long_term=long_term)

    memory = facade.get_long_term()

    assert memory is long_term.get_memory()
    assert "users" in memory
    assert "Nolan" in memory["users"]


def test_memory_facade_shares_composition_root_long_term_instance() -> None:
    """P1-121: facade must reference the same LongTermMemory, not a duplicate."""
    from core.titan import Titan

    titan = Titan()

    assert titan.memory.get_long_term() is titan.long_memory.get_memory()
    assert titan.long_memory is titan.brain.long_memory

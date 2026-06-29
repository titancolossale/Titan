# =====================================
# Titan Memory Command Tests
# =====================================

"""Tests for explicit remember/forget/show commands (P3-030 / P3-031)."""

from __future__ import annotations

from pathlib import Path

from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService


def _service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )


def test_show_memory_command_returns_user_summary(tmp_path: Path) -> None:
    """P3-030: montre ma mémoire returns formatted user memory."""
    service = _service(tmp_path)
    service.maybe_remember("Nolan", "Je préfère Python")

    response = service.handle_command("Nolan", "Montre ma mémoire")

    assert response is not None
    assert "Python" in response


def test_forget_command_removes_matching_items(tmp_path: Path) -> None:
    """P3-030: oublie removes items and confirms in French."""
    service = _service(tmp_path)
    service.maybe_remember("Nolan", "Souviens-toi de mon chat s'appelle Pixel")

    response = service.handle_command("Nolan", "Oublie Pixel")

    assert response is not None
    assert "retiré" in response.lower() or "1" in response
    memory = service.get_document()
    assert not any("Pixel" in str(item) for item in memory["users"]["Nolan"]["notes"])


def test_explicit_remember_command_stores_and_confirms(tmp_path: Path) -> None:
    """P3-031: souviens-toi de stores content and returns confirmation."""
    service = _service(tmp_path)

    response = service.handle_command("Nolan", "Souviens-toi de mon framework favori : FastAPI")

    assert response is not None
    assert "FastAPI" in response
    memory = service.get_document()
    all_items = (
        memory["users"]["Nolan"]["notes"]
        + memory["users"]["Nolan"]["preferences"]
        + memory["users"]["Nolan"]["projects"]
        + memory["users"]["Nolan"]["goals"]
    )
    assert any("FastAPI" in str(item) for item in all_items)


def test_handle_command_returns_none_for_normal_chat(tmp_path: Path) -> None:
    """Non-command messages must not be intercepted."""
    service = _service(tmp_path)

    assert service.handle_command("Nolan", "Bonjour Titan") is None

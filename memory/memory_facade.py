# =====================================
# Titan Memory Facade
# =====================================

"""Backward-compatible alias for MemoryService (Phase 3 — P3-011)."""

from memory.memory_service import MemoryService

MemoryFacade = MemoryService

__all__ = ["MemoryFacade", "MemoryService"]

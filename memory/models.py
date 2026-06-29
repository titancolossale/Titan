# =====================================
# Titan Memory Models
# =====================================

"""Typed structures for the memory service API (Phase 3 — P3-010)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    """Structured output from memory retrieval for prompt injection."""

    text: str
    items: list[str] = field(default_factory=list)
    user: str = ""

    @property
    def has_matches(self) -> bool:
        """True when at least one relevant memory item was found."""
        return bool(self.items)

# =====================================
# Titan Tool Schema
# =====================================

"""Declarative tool input schemas (Phase 10A — P10A-002)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolParameter:
    """Single parameter definition for tool input validation."""

    name: str
    param_type: str
    description: str
    required: bool = True
    default: object = None


@dataclass
class ToolSchema:
    """Declarative schema describing tool name, purpose, and parameters."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

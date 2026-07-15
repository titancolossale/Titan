# =====================================
# Titan Tool Metadata
# =====================================

"""Structured metadata describing a registered Titan tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.tools.base_tool import BaseTool


@dataclass(frozen=True)
class ToolMetadata:
    """Immutable snapshot of a tool's registry metadata."""

    id: str
    name: str
    description: str
    category: str
    version: str
    author: str
    enabled: bool
    requires_confirmation: bool
    capabilities: list[str] = field(default_factory=list)

    @classmethod
    def from_tool(cls, tool: BaseTool, *, author: str = "Titan") -> ToolMetadata:
        """Build metadata from a live tool instance."""
        return cls(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            category=tool.category,
            version=tool.version,
            author=author,
            enabled=tool.enabled,
            requires_confirmation=tool.requires_confirmation,
            capabilities=list(tool.capabilities),
        )

# =====================================
# Titan Core Tool Registry Exceptions
# =====================================

"""Custom exceptions for the core tool registry layer."""

from __future__ import annotations

from core.exceptions import ToolError


class ToolRegistryError(ToolError):
    """Base exception for core tool registry failures."""


class ToolAlreadyRegisteredError(ToolRegistryError):
    """Raised when registering a tool whose id is already in the registry."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool already registered: {tool_id}")


class ToolNotRegisteredError(ToolRegistryError):
    """Raised when a tool id is not present in the registry."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool not registered: {tool_id}")

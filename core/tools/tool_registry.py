# =====================================
# Titan Core Tool Registry
# =====================================

"""Central registry for Titan tool discovery, enablement, and lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.tools.base_tool import BaseTool
from core.tools.exceptions import ToolAlreadyRegisteredError, ToolNotRegisteredError
from core.tools.tool_metadata import ToolMetadata

if TYPE_CHECKING:
    from core.tools.capability_registry import CapabilityRegistry


class ToolRegistry:
    """Register and manage Titan tools indexed by tool id."""

    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._capability_registry = capability_registry

    @property
    def capability_registry(self) -> CapabilityRegistry | None:
        """Optional shared capability registry synced on register/unregister."""
        return self._capability_registry

    def attach_capability_registry(self, capability_registry: CapabilityRegistry) -> None:
        """Attach a capability registry and publish metadata for existing tools."""
        self._capability_registry = capability_registry
        for tool in self.list_tools():
            if capability_registry.get_tool(tool.id) is None:
                capability_registry.register_tool(tool)

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool instance.

        Args:
            tool: Tool to add to the registry.

        Raises:
            ToolAlreadyRegisteredError: If ``tool.id`` is already registered.
        """
        tool_id = tool.id
        if tool_id in self._tools:
            raise ToolAlreadyRegisteredError(tool_id)
        self._tools[tool_id] = tool
        if self._capability_registry is not None:
            self._capability_registry.register_tool(tool)

    def unregister_tool(self, tool_id: str) -> None:
        """Remove a tool from the registry.

        Args:
            tool_id: Registry key of the tool to remove.

        Raises:
            ToolNotRegisteredError: If ``tool_id`` is not registered.
        """
        if tool_id not in self._tools:
            raise ToolNotRegisteredError(tool_id)
        del self._tools[tool_id]
        if self._capability_registry is not None:
            self._capability_registry.unregister_tool(tool_id)

    def get_tool(self, tool_id: str) -> BaseTool | None:
        """Return a registered tool by id, or ``None`` if absent."""
        return self._tools.get(tool_id)

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools sorted by id."""
        return [self._tools[key] for key in sorted(self._tools)]

    def list_enabled_tools(self) -> list[BaseTool]:
        """Return registered tools whose ``enabled`` flag is True."""
        return [tool for tool in self.list_tools() if tool.enabled]

    def list_tools_by_category(self, category: str) -> list[BaseTool]:
        """Return registered tools matching the given category."""
        normalized = category.strip().lower()
        return [
            tool
            for tool in self.list_tools()
            if tool.category.strip().lower() == normalized
        ]

    def list_tool_metadata(self) -> list[ToolMetadata]:
        """Return metadata snapshots for all registered tools."""
        return [tool.to_metadata() for tool in self.list_tools()]

    def enable_tool(self, tool_id: str) -> None:
        """Mark a registered tool as enabled.

        Raises:
            ToolNotRegisteredError: If ``tool_id`` is not registered.
        """
        tool = self._require_tool(tool_id)
        tool.enabled = True

    def disable_tool(self, tool_id: str) -> None:
        """Mark a registered tool as disabled.

        Raises:
            ToolNotRegisteredError: If ``tool_id`` is not registered.
        """
        tool = self._require_tool(tool_id)
        tool.enabled = False

    def tool_exists(self, tool_id: str) -> bool:
        """Return True when ``tool_id`` is registered."""
        return tool_id in self._tools

    def _require_tool(self, tool_id: str) -> BaseTool:
        """Return a registered tool or raise ToolNotRegisteredError."""
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotRegisteredError(tool_id)
        return tool

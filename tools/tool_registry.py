# =====================================
# Titan Tool Registry
# =====================================

"""Central registry for tool registration and dispatch (Phase 6 — P6-011)."""

from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_result import ToolResult


class ToolRegistry:
    """Register tools by name and execute with schema validation."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool; later registration for same name raises."""
        name = tool.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Return a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return sorted registered tool names."""
        return sorted(self._tools.keys())

    def run(self, name: str, params: dict | None = None) -> ToolResult:
        """Validate params and execute the named tool."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"Outil inconnu : {name}",
                source="registry",
            )
        call_params = dict(params or {})
        validation_error = tool.validate_params(call_params)
        if validation_error:
            return ToolResult(
                tool_name=name,
                success=False,
                error=validation_error,
                source=name,
            )
        try:
            return tool.run(**call_params)
        except Exception as exc:
            return ToolResult(
                tool_name=name,
                success=False,
                error=str(exc),
                source=name,
            )

# =====================================
# Titan Base Tool
# =====================================

"""Abstract tool contract and input schema (Phase 6 — P6-010; Phase 10A schema extract)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tools.tool_result import ToolResult
from tools.tool_schema import ToolParameter, ToolSchema

__all__ = ["BaseTool", "ToolParameter", "ToolSchema"]


class BaseTool(ABC):
    """Discrete external capability invoked by Brain or authorized agents."""

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's input/output schema."""

    @abstractmethod
    def run(self, **params: object) -> ToolResult:
        """Execute the tool with validated parameters."""

    @property
    def name(self) -> str:
        """Registry key for this tool."""
        return self.schema.name

    def validate_params(self, params: dict) -> str | None:
        """Return an error message if params are invalid, else None."""
        schema = self.schema
        for param_def in schema.parameters:
            if param_def.required and param_def.name not in params:
                if param_def.default is None:
                    return f"Paramètre requis manquant : {param_def.name}"
        for key in params:
            if key.startswith("_"):
                continue
            known = {p.name for p in schema.parameters}
            if key not in known:
                return f"Paramètre inconnu : {key}"
        return None

    def _result(
        self,
        *,
        success: bool,
        data: str = "",
        error: str = "",
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=success,
            data=data,
            error=error,
            source=self.name,
        )

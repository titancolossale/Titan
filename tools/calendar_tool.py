# =====================================
# Titan Calendar Tool (Stub)
# =====================================

"""Calendar stub — interface only until future integration (Phase 6 — P6-025)."""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.tool_result import ToolResult


class CalendarTool(BaseTool):
    """Placeholder for future calendar integration."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="calendar",
            description="Accès calendrier (non implémenté — phase future).",
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description="Action calendrier (list, create, etc.).",
                    required=False,
                    default="list",
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = str(params.get("action", "list"))
        return self._result(
            success=False,
            error=f"calendar non disponible (stub Phase 6). Action : {action!r}",
        )

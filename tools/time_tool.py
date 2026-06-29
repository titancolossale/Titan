# =====================================
# Titan Time Tool
# =====================================

"""Current datetime tool (Phase 6 — P6-012)."""

from __future__ import annotations

from datetime import datetime

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.tool_result import ToolResult


class TimeTool(BaseTool):
    """Return the current local date and time as a formatted string."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="time",
            description="Retourne la date et l'heure actuelles.",
            parameters=[],
        )

    def run(self, **params: object) -> ToolResult:
        del params
        now = datetime.now()
        formatted = now.strftime("%Y-%m-%d %H:%M:%S")
        return self._result(success=True, data=formatted)

    def get_current_time(self) -> str:
        """Backward-compatible facade used by Titan shell startup."""
        return self.run().data

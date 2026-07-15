# =====================================
# Titan Executor
# =====================================

"""Map reasoning analysis to tool requests (Phase 6 — P6-033)."""

from __future__ import annotations

from tools.tool_result import ToolRequest


class Executor:
    """Select execution strategy and surface tool requests for dispatch."""

    def plan_tools(self, analysis: dict) -> list[ToolRequest]:
        """Return tool requests when reasoning signals needs_tool."""
        if not analysis.get("needs_tool"):
            return []
        requests = analysis.get("tool_requests")
        if not isinstance(requests, list):
            return []
        return list(requests)

    def execute(self, analysis: dict) -> str:
        """Human-readable action label for debug logging."""
        if analysis.get("needs_tool"):
            names = [
                req.tool_name
                for req in self.plan_tools(analysis)
            ]
            if names:
                return f"Utiliser outil(s) : {', '.join(names)}"
            return "Utiliser un outil"

        if analysis.get("needs_memory"):
            return "Consulter la mémoire"

        if analysis.get("needs_clarification"):
            return "Poser une question"

        if analysis.get("modification_plan") is not None:
            return "Planifier modification workspace (sans écriture)"

        return "Répondre directement"

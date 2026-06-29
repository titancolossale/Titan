# =====================================
# Titan Execution Policy
# =====================================

"""Execution limits and ordering rules (Phase 8 — P8-060)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPolicy:
    """Policy constraints for agent and tool dispatch."""

    max_agents: int = 3
    max_tools: int = 3
    agents_before_tools: bool = True

    def clamp_agent_count(self, count: int) -> int:
        return max(0, min(count, self.max_agents))

    def clamp_tool_count(self, count: int) -> int:
        return max(0, min(count, self.max_tools))

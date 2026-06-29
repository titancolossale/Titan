# =====================================
# Titan Execution Result
# =====================================

"""Unified execution output from agents and tools (Phase 8 — P8-061)."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.agent_result import AgentResult
from tools.decision.models import ToolDecisionReport
from tools.tool_result import ToolResult


@dataclass
class ExecutionResult:
    """Combined agent and tool execution artifacts for prompt injection."""

    agent_results: list[AgentResult] = field(default_factory=list)
    agent_results_text: str = ""
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_results_text: str = ""
    agents_truncated: int = 0
    tools_truncated: int = 0
    action_label: str = ""
    decision_report: ToolDecisionReport | None = None

    @property
    def has_output(self) -> bool:
        return bool(self.agent_results_text or self.tool_results_text)

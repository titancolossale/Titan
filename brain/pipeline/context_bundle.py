# =====================================
# Titan Think Context Bundle
# =====================================

"""Typed data bundle passed between Brain pipeline stages (Phase 2 — P2-010)."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.agent_result import AgentResult
from context.models import ContextSnapshot
from tools.decision.models import ToolDecisionReport
from tools.tool_result import ToolRequest, ToolResult


@dataclass
class ThinkContext:
    """Mutable context accumulated across the think() pipeline."""

    user_message: str
    current_user: str = "Nolan"
    context_snapshot: ContextSnapshot | None = None
    situational_context: str = ""
    retrieved_memory: str = ""
    state: dict = field(default_factory=dict)
    mission: dict = field(default_factory=dict)
    executive_analysis: str = ""
    structured_plan_text: str = ""
    agent_results: list[AgentResult] = field(default_factory=list)
    agent_results_text: str = ""
    conversation_window: list[str] = field(default_factory=list)
    knowledge_hits: str | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_results_text: str = ""
    tool_status_text: str = ""
    session_id: str = ""
    turn_id: str = ""
    tool_confirmed: bool = False
    confirmation_token: str | None = None
    confirmed_tool_requests: list[ToolRequest] = field(default_factory=list)
    decision_report: ToolDecisionReport | None = None
    initiative_text: str = ""
    learning_text: str = ""
    active_project: str = ""
    skip_llm: bool = False
    prompt: str = ""
    response: str = ""

# =====================================
# Titan Agent Manager
# =====================================

"""Agent registry, dispatch, and auto-selection (Phase 5 — P5-023)."""

from __future__ import annotations

import logging

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.agent_result import AgentResult
from agents.agent_selector import AgentSelector
from agents.automation_agent import AutomationAgent
from agents.base_agent import BaseAgent
from agents.coding_agent import CodingAgent
from agents.general_agent import GeneralAgent
from agents.memory_agent import MemoryAgent
from agents.planning_agent import PlanningAgent
from agents.reasoning_agent import ReasoningAgent
from agents.research_agent import ResearchAgent
from agents.web_agent import WebAgent
from brain.autonomy_policy import AutonomyPolicy
from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)


class AgentManager:

    def __init__(
        self,
        selector: AgentSelector | None = None,
        agent_llm: AgentLLM | None = None,
        memory_service: MemoryService | None = None,
        autonomy_policy: AutonomyPolicy | None = None,
    ) -> None:
        self.agents: dict[str, BaseAgent] = {}
        self.selector = selector or AgentSelector()
        self.agent_llm = agent_llm or AgentLLM()
        self._memory_service = memory_service
        self._autonomy_policy = autonomy_policy

        self._register_defaults()
        if memory_service is not None:
            self.register_agent(
                "memory",
                MemoryAgent(memory_service, self.agent_llm),
            )

    def _register_defaults(self) -> None:
        llm = self.agent_llm
        self.register_agent("base", GeneralAgent(llm))
        self.register_agent("coding", CodingAgent(llm))
        self.register_agent("research", ResearchAgent(llm))
        self.register_agent("planning", PlanningAgent(llm))
        self.register_agent("reasoning", ReasoningAgent(llm))
        self.register_agent("web", WebAgent())
        policy = self._autonomy_policy or AutonomyPolicy.from_settings()
        self.register_agent("automation", AutomationAgent(policy))

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        self.agents[name] = agent

    def list_agents(self) -> list[str]:
        return list(self.agents.keys())

    def get_agent(self, name: str) -> BaseAgent | None:
        return self.agents.get(name)

    def execute(
        self,
        agent_name: str,
        task: str,
        context: AgentContext | None = None,
    ) -> AgentResult:
        agent = self.get_agent(agent_name)

        if agent is None:
            return AgentResult(
                agent_name=agent_name,
                task=task,
                summary="Agent introuvable.",
                confidence=0.0,
            )

        logger.debug("Agent %s executing task: %s", agent_name, task)
        output = agent.execute(task, context)
        return BaseAgent.coerce_result(agent_name, task, output)

    def auto_execute(
        self,
        task: str,
        context: AgentContext | None = None,
    ) -> AgentResult:
        agent_name = self.selector.select_agent(task)
        logger.info("Agent sélectionné : %s", agent_name)
        return self.execute(agent_name, task, context)

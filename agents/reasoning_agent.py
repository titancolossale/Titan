# =====================================
# Titan Reasoning Agent
# =====================================

from agents.agent_context import AgentContext
from agents.agent_llm import AgentLLM
from agents.agent_result import AgentResult
from agents.base_agent import BaseAgent
from agents.llm_agent_mixin import LLMAgentMixin


class ReasoningAgent(LLMAgentMixin, BaseAgent):

    def __init__(self, agent_llm: AgentLLM | None = None) -> None:
        super().__init__("Titan Reasoning Agent", agent_key="reasoning")
        self._agent_llm = agent_llm

    def _execute(self, task: str, context: AgentContext) -> AgentResult:
        return self.run_llm(task, context)

# =====================================
# Titan Task Orchestrator
# =====================================

"""Multi-agent task pipeline — sequential execution with graceful agent error handling."""

from __future__ import annotations

import logging

from agents.agent_context import AgentContext
from agents.agent_result import AgentResult

logger = logging.getLogger(__name__)


class TaskOrchestrator:

    def __init__(self, task_manager, agent_manager):
        self.task_manager = task_manager
        self.agent_manager = agent_manager

    def orchestrate(
        self,
        message: str,
        agent_context: AgentContext | None = None,
    ) -> list[AgentResult]:
        logger.debug("TASK ORCHESTRATOR — starting")

        tasks = self.task_manager.create_tasks(message)

        for agent_name, task in tasks:
            logger.debug("Tâche planifiée — %s : %s", agent_name, task)

        results: list[AgentResult] = []

        for agent_name, task in tasks:
            logger.info("Agent en cours : %s", agent_name)

            ctx = agent_context
            if ctx is not None:
                ctx = AgentContext(
                    user_message=ctx.user_message,
                    task=task,
                    current_user=ctx.current_user,
                    situational_context=ctx.situational_context,
                    retrieved_memory=ctx.retrieved_memory,
                    state=ctx.state,
                    mission=ctx.mission,
                    executive_analysis=ctx.executive_analysis,
                    active_project=ctx.active_project,
                    current_phase=ctx.current_phase,
                    current_goal=ctx.current_goal,
                )

            try:
                result = self.agent_manager.execute(agent_name, task, ctx)
            except Exception as exc:
                logger.error(
                    "Agent %s failed during orchestration: %s",
                    agent_name,
                    exc,
                    exc_info=True,
                )
                result = AgentResult(
                    agent_name=agent_name,
                    task=task,
                    summary=f"Erreur agent {agent_name}: {exc}",
                    confidence=0.0,
                )

            results.append(result)
            logger.debug("Résultat reçu de %s", agent_name)

        return results

    def format_results(self, results: list[AgentResult]) -> str:
        final_text = ""

        for item in results:
            final_text += f"""
==============================
AGENT : {item.agent_name}
==============================

Tâche :
{item.task}

Résultat :
{item.result}

"""

        return final_text

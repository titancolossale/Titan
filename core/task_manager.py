# =====================================
# Titan Task Manager
# =====================================

"""Multi-agent task creation via unified routing registry (Phase 5 — P5-012)."""

from __future__ import annotations

from agents.agent_registry import AgentRegistry, default_registry


class TaskManager:
    """Builds ordered agent task tuples from user messages."""

    def __init__(
        self,
        agent_manager,
        registry: AgentRegistry | None = None,
    ) -> None:
        self.agent_manager = agent_manager
        self._registry = registry or default_registry

    def create_tasks(self, message: str) -> list[tuple[str, str]]:
        return self._registry.create_tasks(message)

    def execute_tasks(self, message: str):
        """Legacy helper — prefer TaskOrchestrator for production paths."""
        tasks = self.create_tasks(message)

        results = []

        print("Tâches créées :")
        for agent_name, task in tasks:
            print(f"- {agent_name} : {task}")
        print()

        for agent_name, task in tasks:
            print(f"Exécution de l'agent : {agent_name}")
            result = self.agent_manager.execute(agent_name, task)
            results.append((agent_name, result))
            print(result)
            print()

        return results

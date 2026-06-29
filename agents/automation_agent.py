# =====================================
# Titan Automation Agent
# =====================================

"""Multi-step workflow agent with confirmation gates (Phase 9 — P9-082)."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.agent_context import AgentContext
from agents.agent_result import AgentResult
from agents.base_agent import BaseAgent
from brain.autonomy_policy import AutonomousActionType, AutonomyPolicy


@dataclass
class AutomationStep:
    """One step in a planned automation workflow."""

    action: str
    description: str
    action_type: AutonomousActionType = AutonomousActionType.AUTOMATION
    requires_confirmation: bool = True
    params: dict = field(default_factory=dict)


class AutomationAgent(BaseAgent):
    """Plans scripted workflows; enforces autonomy confirmation policy."""

    def __init__(self, policy: AutonomyPolicy | None = None) -> None:
        super().__init__("Titan Automation Agent", agent_key="automation")
        self._policy = policy or AutonomyPolicy.from_settings()

    def _execute(self, task: str, context: AgentContext) -> AgentResult:
        steps = self.plan_workflow(task, context)
        pending = [step for step in steps if step.requires_confirmation]
        auto_steps = [step for step in steps if not step.requires_confirmation]

        lines = [
            f"Workflow automation ({len(steps)} étape(s)) :",
        ]
        for index, step in enumerate(steps, start=1):
            gate = "confirmation requise" if step.requires_confirmation else "auto"
            lines.append(f"  {index}. [{gate}] {step.description}")

        if pending:
            lines.append("")
            lines.append(
                f"{len(pending)} étape(s) nécessitent confirmation utilisateur "
                "(politique d'autonomie active)."
            )
        if auto_steps:
            lines.append(
                f"{len(auto_steps)} étape(s) peuvent s'exécuter sans confirmation."
            )

        content = "\n".join(lines)
        step_artifacts = [
            f"{step.action}: {step.description} "
            f"({'confirmation' if step.requires_confirmation else 'auto'})"
            for step in steps
        ]
        return AgentResult(
            agent_name=self.agent_key,
            task=task,
            summary=f"Plan automation : {len(steps)} étape(s), {len(pending)} en attente.",
            artifacts=[content, *step_artifacts],
            confidence=0.75 if steps else 0.3,
        )

    def plan_workflow(self, task: str, context: AgentContext) -> list[AutomationStep]:
        """Build a workflow plan from task keywords — extensible for LLM planning."""
        task_lower = task.lower()
        steps: list[AutomationStep] = []

        if any(word in task_lower for word in ("fichier", "file", "écrire", "write")):
            steps.append(
                AutomationStep(
                    action="file_write",
                    description="Écrire ou modifier un fichier",
                    action_type=AutonomousActionType.FILE_WRITE,
                    requires_confirmation=self._policy.requires_confirmation(
                        AutonomousActionType.FILE_WRITE,
                    ),
                ),
            )

        if any(word in task_lower for word in ("python", "script", "exécuter", "exec")):
            steps.append(
                AutomationStep(
                    action="python_exec",
                    description="Exécuter un script Python",
                    action_type=AutonomousActionType.PYTHON_EXEC,
                    requires_confirmation=self._policy.requires_confirmation(
                        AutonomousActionType.PYTHON_EXEC,
                    ),
                ),
            )

        if any(word in task_lower for word in ("web", "recherche", "search", "internet")):
            steps.append(
                AutomationStep(
                    action="web_search",
                    description="Rechercher des informations web",
                    action_type=AutonomousActionType.WEB_SEARCH,
                    requires_confirmation=self._policy.requires_confirmation(
                        AutonomousActionType.WEB_SEARCH,
                    ),
                ),
            )

        if any(word in task_lower for word in ("planifier", "schedule", "rappel", "reminder")):
            steps.append(
                AutomationStep(
                    action="schedule_job",
                    description="Planifier une tâche autonome",
                    action_type=AutonomousActionType.SCHEDULED_JOB,
                    requires_confirmation=self._policy.requires_confirmation(
                        AutonomousActionType.SCHEDULED_JOB,
                    ),
                ),
            )

        if not steps:
            steps.append(
                AutomationStep(
                    action="analyze",
                    description=f"Analyser la demande : {task[:80]}",
                    action_type=AutonomousActionType.AUTOMATION,
                    requires_confirmation=self._policy.requires_confirmation(
                        AutonomousActionType.AUTOMATION,
                    ),
                ),
            )

        _ = context
        return steps

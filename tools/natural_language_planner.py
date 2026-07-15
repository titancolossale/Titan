# =====================================
# Titan Natural Language Planner
# =====================================

"""Transform natural language requests into structured execution plans (Phase 12.6 Batch 2 — P126-011)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tools.decision.models import ToolDecisionReport
from tools.decision.task_execution_models import TaskExecutionPlan
from tools.decision.workspace_planner import WorkspacePlan
from tools.permission_manager import PermissionLevel, PermissionManager, resolve_tool_action
from tools.planner_models import (
    ExecutionPlan,
    PlannerResult,
    PlanStep,
    PlanStepKind,
)
from tools.tool_result import ToolRequest

_CONDITIONAL_PATTERNS = (
    re.compile(r"\bsi\b", re.IGNORECASE),
    re.compile(r"\bsinon\b", re.IGNORECASE),
    re.compile(r"\bautrement\b", re.IGNORECASE),
    re.compile(r"\bif\b", re.IGNORECASE),
    re.compile(r"\belse\b", re.IGNORECASE),
    re.compile(r"\botherwise\b", re.IGNORECASE),
    re.compile(r"\bunless\b", re.IGNORECASE),
)

_FALLBACK_PATTERNS = (
    re.compile(r"\bsinon\b", re.IGNORECASE),
    re.compile(r"\bsinon\s+essaie\b", re.IGNORECASE),
    re.compile(r"\bfallback\b", re.IGNORECASE),
    re.compile(r"\botherwise\s+try\b", re.IGNORECASE),
    re.compile(r"\belse\s+try\b", re.IGNORECASE),
)


def compute_execution_order(steps: tuple[PlanStep, ...]) -> tuple[str, ...]:
    """Topologically sort steps by dependencies; preserve declaration order on ties."""
    if not steps:
        return ()

    step_ids = [step.step_id for step in steps]
    dependents: dict[str, set[str]] = {step_id: set() for step_id in step_ids}
    indegree: dict[str, int] = {step_id: 0 for step_id in step_ids}

    for step in steps:
        for dependency in step.dependencies:
            if dependency not in indegree:
                continue
            dependents[dependency].add(step.step_id)
            indegree[step.step_id] += 1

    ready = [step_id for step_id in step_ids if indegree[step_id] == 0]
    ordered: list[str] = []

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for dependent in sorted(dependents[current], key=step_ids.index):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
        ready.sort(key=step_ids.index)

    if len(ordered) != len(step_ids):
        return tuple(step_ids)
    return tuple(ordered)


def identify_independent_steps(steps: tuple[PlanStep, ...]) -> tuple[str, ...]:
    """Return step IDs with no dependencies (may run in parallel conceptually)."""
    return tuple(step.step_id for step in steps if not step.dependencies)


def identify_sequential_steps(steps: tuple[PlanStep, ...]) -> tuple[str, ...]:
    """Return step IDs that depend on at least one prior step."""
    return tuple(step.step_id for step in steps if step.dependencies)


@dataclass
class NaturalLanguagePlanner:
    """Break complex user requests into executable multi-step plans."""

    permission_manager: PermissionManager = field(default_factory=PermissionManager)

    def plan(
        self,
        message: str,
        analysis: dict[str, Any],
        *,
        decision_report: ToolDecisionReport | None = None,
    ) -> PlannerResult:
        """Build a structured execution plan from a user message and reasoning analysis."""
        report = decision_report or analysis.get("decision_report")
        if not isinstance(report, ToolDecisionReport):
            report = None

        if analysis.get("needs_clarification"):
            return self._empty_result(
                message,
                summary="Clarification requise avant exécution d'outils.",
            )

        task_plan = analysis.get("task_execution_plan")
        if isinstance(task_plan, TaskExecutionPlan):
            return self._plan_from_task_execution(message, task_plan, report)

        workspace_plan = analysis.get("workspace_plan")
        if isinstance(workspace_plan, WorkspacePlan) and workspace_plan.chain_after_search:
            return self._plan_search_then_read(message, workspace_plan, report)

        tool_requests = analysis.get("tool_requests") or []
        if not isinstance(tool_requests, list) or not tool_requests:
            goal = str(analysis.get("goal", message)).strip() or message
            return self._empty_result(goal, summary="Aucun outil requis pour cette demande.")

        if self._has_conditional_language(message):
            return self._plan_conditional(message, tool_requests, report)

        if len(tool_requests) == 1:
            return self._plan_single_step(message, tool_requests[0], report)

        return self._plan_multi_step(message, tool_requests, report)

    def to_tool_requests(self, planner_result: PlannerResult) -> list[ToolRequest]:
        """Convert a planner result into ordered ToolRequest objects for orchestration."""
        step_by_id = {step.step_id: step for step in planner_result.steps}
        requests: list[ToolRequest] = []
        for step_id in planner_result.execution_order:
            step = step_by_id.get(step_id)
            if step is None:
                continue
            if step.step_kind == PlanStepKind.CONDITIONAL:
                continue
            requests.append(
                ToolRequest(step.required_tool, dict(step.tool_params)),
            )
        return requests

    def _empty_result(self, goal: str, *, summary: str) -> PlannerResult:
        plan = ExecutionPlan(
            overall_goal=goal,
            plan_summary=summary,
            steps=(),
            execution_order=(),
        )
        return PlannerResult.from_execution_plan(plan, requires_confirmation=False)

    def _plan_single_step(
        self,
        message: str,
        request: ToolRequest,
        decision_report: ToolDecisionReport | None,
    ) -> PlannerResult:
        step = self._build_step(
            step_id="step_1",
            objective=self._step_objective(message, request),
            reasoning="Demande simple mappée à un seul outil.",
            request=request,
            decision_report=decision_report,
        )
        execution_order = compute_execution_order((step,))
        plan = ExecutionPlan(
            overall_goal=message.strip(),
            plan_summary=f"Exécution en 1 étape via {request.tool_name}.",
            steps=(step,),
            execution_order=execution_order,
        )
        requires_confirmation = step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
        return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)

    def _plan_multi_step(
        self,
        message: str,
        requests: list[ToolRequest],
        decision_report: ToolDecisionReport | None,
    ) -> PlannerResult:
        steps: list[PlanStep] = []
        previous_id: str | None = None
        for index, request in enumerate(requests, start=1):
            step_id = f"step_{index}"
            dependencies: tuple[str, ...] = ()
            if previous_id is not None:
                dependencies = (previous_id,)
            step = self._build_step(
                step_id=step_id,
                objective=self._step_objective(message, request, index=index),
                reasoning=(
                    "Étape séquentielle : dépend du résultat de l'étape précédente."
                    if dependencies
                    else "Étape indépendante dans une séquence multi-outils."
                ),
                request=request,
                decision_report=decision_report,
                dependencies=dependencies,
            )
            steps.append(step)
            previous_id = step_id

        step_tuple = tuple(steps)
        execution_order = compute_execution_order(step_tuple)
        tools = ExecutionPlan(
            overall_goal=message.strip(),
            plan_summary="",
            steps=step_tuple,
            execution_order=execution_order,
        ).estimated_tools
        plan = ExecutionPlan(
            overall_goal=message.strip(),
            plan_summary=(
                f"Exécution en {len(steps)} étapes séquentielles "
                f"({', '.join(tools)})."
            ),
            steps=step_tuple,
            execution_order=execution_order,
        )
        requires_confirmation = any(
            step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
            for step in steps
        )
        return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)

    def _plan_search_then_read(
        self,
        message: str,
        workspace_plan: WorkspacePlan,
        decision_report: ToolDecisionReport | None,
    ) -> PlannerResult:
        search_request = next(
            (
                request
                for request in workspace_plan.tool_requests
                if request.params.get("action") == "search_files"
            ),
            workspace_plan.tool_requests[0] if workspace_plan.tool_requests else None,
        )
        if search_request is None:
            return self._empty_result(message, summary="Plan workspace sans recherche.")

        search_step = self._build_step(
            step_id="search",
            objective="Rechercher des fichiers pertinents dans le workspace.",
            reasoning="Première étape indépendante : localiser les fichiers cibles.",
            request=search_request,
            decision_report=decision_report,
            expected_output="Liste de fichiers correspondant à la requête.",
        )
        read_params = {"action": "read_file"}
        if workspace_plan.selected_file:
            read_params["path"] = workspace_plan.selected_file
        read_step = self._build_step(
            step_id="read",
            objective="Lire le fichier sélectionné après la recherche.",
            reasoning="Étape conditionnelle dépendant des résultats de recherche.",
            request=ToolRequest("file_read", read_params),
            decision_report=decision_report,
            dependencies=("search",),
            step_kind=PlanStepKind.CONDITIONAL,
            condition="search_has_results",
            expected_output="Contenu du fichier lu pour explication.",
        )
        steps = (search_step, read_step)
        execution_order = compute_execution_order(steps)
        plan = ExecutionPlan(
            overall_goal=message.strip(),
            plan_summary=(
                "Recherche workspace puis lecture conditionnelle du fichier trouvé."
            ),
            steps=steps,
            execution_order=execution_order,
        )
        requires_confirmation = any(
            step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
            for step in steps
        )
        return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)

    def _plan_conditional(
        self,
        message: str,
        requests: list[ToolRequest],
        decision_report: ToolDecisionReport | None,
    ) -> PlannerResult:
        primary_request = requests[0]
        primary_step = self._build_step(
            step_id="primary",
            objective=self._step_objective(message, primary_request),
            reasoning="Étape principale évaluée en premier.",
            request=primary_request,
            decision_report=decision_report,
        )

        fallback_step: PlanStep | None = None
        if len(requests) > 1:
            fallback_request = requests[1]
            fallback_step = self._build_step(
                step_id="fallback",
                objective=self._step_objective(message, fallback_request, index=2),
                reasoning="Étape de repli si l'étape principale échoue ou ne produit pas de résultat.",
                request=fallback_request,
                decision_report=decision_report,
                dependencies=("primary",),
                step_kind=PlanStepKind.FALLBACK,
                condition="primary_failed",
                fallback_tool=fallback_request.tool_name,
                fallback_params=dict(fallback_request.params),
            )
        elif self._has_fallback_language(message):
            fallback_step = PlanStep(
                step_id="fallback",
                objective="Tenter une recherche alternative si la lecture directe échoue.",
                reasoning="Repli heuristique basé sur le langage conditionnel de la demande.",
                required_tool="file_read",
                required_permission=PermissionLevel.AUTO_ALLOWED,
                expected_output="Résultats de recherche de repli.",
                dependencies=("primary",),
                tool_params={"action": "search_files", "keyword": message[:80]},
                step_kind=PlanStepKind.FALLBACK,
                condition="primary_failed",
                fallback_tool="file_read",
                fallback_params={"action": "search_files", "keyword": message[:80]},
                selected_action="search_files",
            )

        conditional_step = PlanStep(
            step_id="conditional",
            objective="Exécuter une action seulement si la condition utilisateur est satisfaite.",
            reasoning="Étape conditionnelle déduite du langage si/sinon de la demande.",
            required_tool=primary_step.required_tool,
            required_permission=primary_step.required_permission,
            expected_output=primary_step.expected_output,
            dependencies=("primary",),
            tool_params=dict(primary_step.tool_params),
            step_kind=PlanStepKind.CONDITIONAL,
            condition="user_condition_met",
            selected_action=primary_step.selected_action,
        )

        steps_list = [primary_step, conditional_step]
        if fallback_step is not None:
            primary_with_fallback = PlanStep(
                step_id=primary_step.step_id,
                objective=primary_step.objective,
                reasoning=primary_step.reasoning,
                required_tool=primary_step.required_tool,
                required_permission=primary_step.required_permission,
                expected_output=primary_step.expected_output,
                dependencies=primary_step.dependencies,
                tool_params=primary_step.tool_params,
                step_kind=PlanStepKind.STANDARD,
                selected_action=primary_step.selected_action,
                fallback_step_id=fallback_step.step_id,
                fallback_tool=fallback_step.required_tool,
                fallback_params=dict(fallback_step.tool_params),
            )
            steps_list[0] = primary_with_fallback
            steps_list.append(fallback_step)

        steps = tuple(steps_list)
        execution_order = compute_execution_order(steps)
        plan = ExecutionPlan(
            overall_goal=message.strip(),
            plan_summary="Plan conditionnel avec étapes principale, conditionnelle et repli.",
            steps=steps,
            execution_order=execution_order,
        )
        requires_confirmation = any(
            step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
            for step in steps
        )
        return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)

    def _plan_from_task_execution(
        self,
        message: str,
        task_plan: TaskExecutionPlan,
        decision_report: ToolDecisionReport | None,
    ) -> PlannerResult:
        steps: list[PlanStep] = []
        for step_def in task_plan.steps:
            request = ToolRequest(step_def.tool, dict(step_def.inputs))
            step = self._build_step(
                step_id=step_def.step_id,
                objective=f"Exécuter {step_def.tool} pour {task_plan.objective}.",
                reasoning="Étape importée depuis TaskExecutionPlan.",
                request=request,
                decision_report=decision_report,
                dependencies=step_def.depends_on,
                expected_output=step_def.expected_output or f"Sortie de {step_def.step_id}",
            )
            if step_def.fallback_tool:
                step = PlanStep(
                    step_id=step.step_id,
                    objective=step.objective,
                    reasoning=step.reasoning,
                    required_tool=step.required_tool,
                    required_permission=step.required_permission,
                    expected_output=step.expected_output,
                    dependencies=step.dependencies,
                    tool_params=step.tool_params,
                    step_kind=PlanStepKind.FALLBACK,
                    fallback_step_id=f"{step_def.step_id}_fallback",
                    fallback_tool=step_def.fallback_tool,
                    fallback_params=(
                        dict(step_def.fallback_inputs)
                        if step_def.fallback_inputs is not None
                        else None
                    ),
                    selected_action=step.selected_action,
                )
            steps.append(step)

        step_tuple = tuple(steps)
        execution_order = compute_execution_order(step_tuple)
        plan = ExecutionPlan(
            overall_goal=task_plan.objective or message.strip(),
            plan_summary=f"Plan multi-étapes ({len(steps)} étapes) pour {task_plan.objective}.",
            steps=step_tuple,
            execution_order=execution_order,
        )
        requires_confirmation = any(
            step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED
            for step in steps
        )
        return PlannerResult.from_execution_plan(plan, requires_confirmation=requires_confirmation)

    def _build_step(
        self,
        *,
        step_id: str,
        objective: str,
        reasoning: str,
        request: ToolRequest,
        decision_report: ToolDecisionReport | None,
        dependencies: tuple[str, ...] = (),
        step_kind: PlanStepKind = PlanStepKind.STANDARD,
        condition: str = "",
        expected_output: str = "",
    ) -> PlanStep:
        action = resolve_tool_action(
            request.tool_name,
            request.params,
            decision_report,
        )
        permission = self.permission_manager.evaluate(
            request.tool_name,
            action,
            request.params,
            decision_report=decision_report,
        )
        if not expected_output:
            expected_output = f"Résultat de {action} via {request.tool_name}."
        return PlanStep(
            step_id=step_id,
            objective=objective,
            reasoning=reasoning,
            required_tool=request.tool_name,
            required_permission=permission.level,
            expected_output=expected_output,
            dependencies=dependencies,
            tool_params=dict(request.params),
            step_kind=step_kind,
            condition=condition,
            selected_action=action,
        )

    @staticmethod
    def _step_objective(
        message: str,
        request: ToolRequest,
        *,
        index: int | None = None,
    ) -> str:
        action = str(request.params.get("action", request.tool_name))
        prefix = f"Étape {index} : " if index is not None else ""
        snippet = message.strip()[:60]
        if snippet:
            return f"{prefix}{action} pour « {snippet} »."
        return f"{prefix}Exécuter {action} via {request.tool_name}."

    @staticmethod
    def _has_conditional_language(message: str) -> bool:
        return any(pattern.search(message) for pattern in _CONDITIONAL_PATTERNS)

    @staticmethod
    def _has_fallback_language(message: str) -> bool:
        return any(pattern.search(message) for pattern in _FALLBACK_PATTERNS)

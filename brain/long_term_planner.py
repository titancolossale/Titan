# =====================================
# Titan Long-Term Planning Engine
# =====================================

"""Long-Term Planning Engine V1 — high-level objective → structured multi-level plan.

Planning only. Never executes tools, never edits code, never starts missions,
never generates patches. Mission Runtime may later adopt proposed missions;
Executive Function may recommend next work from a GoalPlan without mutating it.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain.developer_workflow import DeveloperWorkflow
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.project_intelligence import ArchitectureSummary, ProjectIntelligence
    from brain.reasoning_models import ReasoningResult
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{3,}", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "what",
        "when",
        "automate",
        "my",
        "our",
        "please",
        "titan",
        "dans",
        "pour",
        "avec",
        "mon",
        "mes",
        "une",
        "des",
        "les",
        "sur",
    }
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskKind(str, Enum):
    """Semantic category of planned work."""

    RESEARCH = "research"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    DEPLOYMENT = "deployment"
    VALIDATION = "validation"
    REVIEW = "review"
    ARCHITECTURE = "architecture"


class TaskStatus(str, Enum):
    """Lifecycle status of a planned task (advisory — not executed)."""

    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskDifficulty(str, Enum):
    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class GoalDomain(str, Enum):
    """Coarse domain used to select decomposition templates."""

    TRADING = "trading"
    AUTOMATION = "automation"
    SOFTWARE = "software"
    INTEGRATION = "integration"
    INFRASTRUCTURE = "infrastructure"
    RESEARCH = "research"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass(frozen=True)
class Dependency:
    """Directed dependency: ``to_id`` cannot start until ``from_id`` finishes."""

    from_id: str
    to_id: str
    kind: str = "finish_to_start"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "kind": self.kind,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SubTask:
    """Finest planning unit under a Task."""

    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    estimated_duration: str = ""
    required_tools: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "estimated_duration": self.estimated_duration,
            "required_tools": list(self.required_tools),
        }


@dataclass(frozen=True)
class Task:
    """Executable-sized work item inside a milestone (plan only)."""

    id: str
    title: str
    description: str
    priority: TaskPriority = TaskPriority.NORMAL
    difficulty: TaskDifficulty = TaskDifficulty.MEDIUM
    estimated_duration: str = ""
    dependencies: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    success_conditions: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.PENDING
    kind: TaskKind = TaskKind.IMPLEMENTATION
    subtasks: tuple[SubTask, ...] = ()
    is_parallel_safe: bool = False
    is_critical_path: bool = False
    is_quick_win: bool = False
    is_high_risk: bool = False
    is_low_risk: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "difficulty": self.difficulty.value,
            "estimated_duration": self.estimated_duration,
            "dependencies": list(self.dependencies),
            "required_tools": list(self.required_tools),
            "success_conditions": list(self.success_conditions),
            "blocked_by": list(self.blocked_by),
            "status": self.status.value,
            "kind": self.kind.value,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "is_parallel_safe": self.is_parallel_safe,
            "is_critical_path": self.is_critical_path,
            "is_quick_win": self.is_quick_win,
            "is_high_risk": self.is_high_risk,
            "is_low_risk": self.is_low_risk,
        }


@dataclass(frozen=True)
class Milestone:
    """Ordered delivery checkpoint within a project."""

    id: str
    title: str
    description: str
    tasks: tuple[Task, ...] = ()
    success_criteria: tuple[str, ...] = ()
    estimated_duration: str = ""
    order: int = 0
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "success_criteria": list(self.success_criteria),
            "estimated_duration": self.estimated_duration,
            "order": self.order,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True)
class ProjectPlan:
    """One project stream under a long-term goal."""

    id: str
    title: str
    description: str
    milestones: tuple[Milestone, ...] = ()
    existing_features: tuple[str, ...] = ()
    missing_systems: tuple[str, ...] = ()
    architecture_conflicts: tuple[str, ...] = ()
    duplicate_work_warnings: tuple[str, ...] = ()
    estimated_duration: str = ""
    priority: TaskPriority = TaskPriority.NORMAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "milestones": [m.to_dict() for m in self.milestones],
            "existing_features": list(self.existing_features),
            "missing_systems": list(self.missing_systems),
            "architecture_conflicts": list(self.architecture_conflicts),
            "duplicate_work_warnings": list(self.duplicate_work_warnings),
            "estimated_duration": self.estimated_duration,
            "priority": self.priority.value,
        }


@dataclass(frozen=True)
class PlanningRisk:
    """Identified planning risk (advisory)."""

    id: str
    summary: str
    severity: str = "medium"
    related_task_ids: tuple[str, ...] = ()
    mitigation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "severity": self.severity,
            "related_task_ids": list(self.related_task_ids),
            "mitigation": self.mitigation,
        }


@dataclass(frozen=True)
class PlanningRecommendation:
    """Advisory next-work recommendation — never mutates the plan."""

    summary: str
    next_task_id: str | None = None
    next_task_title: str | None = None
    rationale: str = ""
    parallel_task_ids: tuple[str, ...] = ()
    avoid_task_ids: tuple[str, ...] = ()
    source: str = "long_term_planner"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "next_task_id": self.next_task_id,
            "next_task_title": self.next_task_title,
            "rationale": self.rationale,
            "parallel_task_ids": list(self.parallel_task_ids),
            "avoid_task_ids": list(self.avoid_task_ids),
            "source": self.source,
        }


@dataclass(frozen=True)
class PlanningSummary:
    """Aggregate quality metrics for a GoalPlan."""

    confidence_score: float
    complexity_score: float
    estimated_implementation_time: str
    reasoning_summary: str
    overall_risk: str
    critical_path_task_ids: tuple[str, ...] = ()
    parallel_groups: tuple[tuple[str, ...], ...] = ()
    sequential_task_ids: tuple[str, ...] = ()
    quick_wins: tuple[str, ...] = ()
    high_risk_tasks: tuple[str, ...] = ()
    low_risk_tasks: tuple[str, ...] = ()
    research_tasks: tuple[str, ...] = ()
    implementation_tasks: tuple[str, ...] = ()
    testing_tasks: tuple[str, ...] = ()
    documentation_tasks: tuple[str, ...] = ()
    deployment_tasks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_score": round(self.confidence_score, 3),
            "complexity_score": round(self.complexity_score, 3),
            "estimated_implementation_time": self.estimated_implementation_time,
            "reasoning_summary": self.reasoning_summary,
            "overall_risk": self.overall_risk,
            "critical_path_task_ids": list(self.critical_path_task_ids),
            "parallel_groups": [list(g) for g in self.parallel_groups],
            "sequential_task_ids": list(self.sequential_task_ids),
            "quick_wins": list(self.quick_wins),
            "high_risk_tasks": list(self.high_risk_tasks),
            "low_risk_tasks": list(self.low_risk_tasks),
            "research_tasks": list(self.research_tasks),
            "implementation_tasks": list(self.implementation_tasks),
            "testing_tasks": list(self.testing_tasks),
            "documentation_tasks": list(self.documentation_tasks),
            "deployment_tasks": list(self.deployment_tasks),
        }


@dataclass(frozen=True)
class MissionProposal:
    """Proposed mission shape for Mission Runtime — never auto-created."""

    title: str
    objective: str
    steps: tuple[str, ...]
    priority: str = "NORMAL"
    success_criteria: str = ""
    source_project_id: str | None = None
    source_milestone_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "objective": self.objective,
            "steps": list(self.steps),
            "priority": self.priority,
            "success_criteria": self.success_criteria,
            "source_project_id": self.source_project_id,
            "source_milestone_id": self.source_milestone_id,
        }

    def to_create_kwargs(self) -> dict[str, Any]:
        """Keyword args compatible with ``MissionRuntime.create_mission``."""
        return {
            "title": self.title,
            "objective": self.objective,
            "steps": list(self.steps),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class GoalPlan:
    """Complete long-term plan for one high-level objective."""

    goal: str
    projects: tuple[ProjectPlan, ...]
    dependencies: tuple[Dependency, ...]
    risks: tuple[PlanningRisk, ...]
    recommendations: tuple[PlanningRecommendation, ...]
    summary: PlanningSummary
    success_criteria: tuple[str, ...]
    required_tools: tuple[str, ...]
    context_summary: str = ""
    mission_proposals: tuple[MissionProposal, ...] = ()
    domain: GoalDomain = GoalDomain.GENERAL
    request: str = ""
    sources: dict[str, Any] = field(default_factory=dict)
    expanded: bool = False

    def all_tasks(self) -> tuple[Task, ...]:
        tasks: list[Task] = []
        for project in self.projects:
            for milestone in project.milestones:
                tasks.extend(milestone.tasks)
        return tuple(tasks)

    def task_by_id(self, task_id: str) -> Task | None:
        for task in self.all_tasks():
            if task.id == task_id:
                return task
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "projects": [p.to_dict() for p in self.projects],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "risks": [r.to_dict() for r in self.risks],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "summary": self.summary.to_dict(),
            "success_criteria": list(self.success_criteria),
            "required_tools": list(self.required_tools),
            "context_summary": self.context_summary,
            "mission_proposals": [m.to_dict() for m in self.mission_proposals],
            "domain": self.domain.value,
            "request": self.request,
            "sources": dict(self.sources),
            "expanded": self.expanded,
        }

    def format_for_prompt(self) -> str:
        lines = [
            "LONG-TERM GOAL PLAN",
            f"- goal: {self.goal}",
            f"- domain: {self.domain.value}",
            f"- projects: {len(self.projects)}",
            f"- confidence: {self.summary.confidence_score:.2f}",
            f"- complexity: {self.summary.complexity_score:.2f}",
            f"- estimated time: {self.summary.estimated_implementation_time}",
            f"- overall risk: {self.summary.overall_risk}",
            f"- context: {self.context_summary}",
        ]
        if self.summary.reasoning_summary:
            lines.append(f"- reasoning: {self.summary.reasoning_summary}")
        if self.recommendations:
            rec = self.recommendations[0]
            lines.append(
                f"- next: {rec.next_task_title or rec.summary}"
            )
        for project in self.projects[:3]:
            lines.append(f"- project: {project.title}")
            for milestone in project.milestones[:4]:
                lines.append(
                    f"  - milestone: {milestone.title} "
                    f"({len(milestone.tasks)} tasks)"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Domain templates (heuristic decomposition)
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: dict[GoalDomain, tuple[str, ...]] = {
    GoalDomain.TRADING: (
        "trading",
        "trade",
        "orr",
        "strategy",
        "broker",
        "rithmic",
        "apex",
        "backtest",
        "market",
        "futures",
        "paper trading",
    ),
    GoalDomain.AUTOMATION: (
        "automate",
        "automation",
        "schedule",
        "cron",
        "workflow",
        "pipeline",
        "bot",
    ),
    GoalDomain.INTEGRATION: (
        "integrate",
        "integration",
        "connect",
        "api",
        "webhook",
        "discord",
        "email",
        "calendar",
        "obsidian",
        "github",
    ),
    GoalDomain.INFRASTRUCTURE: (
        "infra",
        "infrastructure",
        "deploy",
        "deployment",
        "ci",
        "cd",
        "docker",
        "server",
    ),
    GoalDomain.RESEARCH: (
        "research",
        "investigate",
        "analyze",
        "study",
        "explore",
        "compare",
    ),
    GoalDomain.SOFTWARE: (
        "feature",
        "implement",
        "build",
        "refactor",
        "module",
        "code",
        "app",
        "system",
    ),
}


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class LongTermPlanner:
    """Transform a high-level objective into a structured GoalPlan.

    Never executes tools, never mutates missions, never writes files.
    """

    def __init__(
        self,
        *,
        workspace_awareness: WorkspaceAwareness | None = None,
        executive_function: ExecutiveFunction | None = None,
        project_intelligence: ProjectIntelligence | None = None,
        developer_workflow: DeveloperWorkflow | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._executive_function = executive_function
        self._project_intelligence = project_intelligence
        self._developer_workflow = developer_workflow
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager

    # --- Public API ---

    def plan_goal(
        self,
        goal: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        reasoning_result: ReasoningResult | None = None,
        expand: bool = False,
    ) -> GoalPlan:
        """Decompose a high-level objective into a multi-level GoalPlan."""
        request = (goal or "").strip()
        if not request:
            return self._empty_plan(request)

        resolved_user = user or self._resolve_user()
        resolved_project = project_id or self._resolve_project_id()

        snapshot = self._resolve_workspace(
            workspace,
            user=resolved_user,
            project_id=resolved_project,
        )
        evaluation = self._resolve_executive(
            executive_evaluation,
            request,
            user=resolved_user,
            project_id=resolved_project,
            workspace=snapshot,
        )
        architecture = self._analyze_architecture(
            user=resolved_user,
            project_id=resolved_project,
            workspace=snapshot,
            executive_evaluation=evaluation,
        )
        memory_hints = self._retrieve_memory(
            request,
            user=resolved_user,
            project_id=resolved_project,
        )
        workflow_hints = self._workflow_quality_gates(request)

        domain = self._classify_domain(request)
        project_specs = self._decompose_into_projects(request, domain, expand=expand)
        projects = tuple(
            self._build_project_plan(
                spec,
                request=request,
                domain=domain,
                architecture=architecture,
                snapshot=snapshot,
                evaluation=evaluation,
                expand=expand,
                workflow_hints=workflow_hints,
            )
            for spec in project_specs
        )

        all_deps = self._collect_dependencies(projects)
        annotated_projects, critical_ids, parallel_groups = self._annotate_graph(
            projects,
            all_deps,
        )
        risks = self._identify_risks(annotated_projects, architecture, snapshot)
        summary = self._build_summary(
            annotated_projects,
            all_deps,
            critical_ids,
            parallel_groups,
            risks,
            domain=domain,
            expand=expand,
            architecture=architecture,
            snapshot=snapshot,
        )
        success_criteria = self._goal_success_criteria(request, domain, annotated_projects)
        required_tools = self._aggregate_tools(annotated_projects)
        mission_proposals = self._propose_missions(annotated_projects)
        context_summary = self._build_context_summary(
            snapshot,
            evaluation,
            architecture,
            memory_hints,
            reasoning_result=reasoning_result,
        )
        recommendations = self._build_recommendations(
            annotated_projects,
            critical_ids,
            parallel_groups,
            evaluation,
            reasoning_result=reasoning_result,
        )

        plan = GoalPlan(
            goal=self._normalize_goal(request),
            projects=annotated_projects,
            dependencies=all_deps,
            risks=risks,
            recommendations=recommendations,
            summary=summary,
            success_criteria=success_criteria,
            required_tools=required_tools,
            context_summary=context_summary,
            mission_proposals=mission_proposals,
            domain=domain,
            request=request,
            sources={
                "workspace": bool(snapshot),
                "executive_function": evaluation is not None,
                "project_intelligence": architecture is not None,
                "developer_workflow": bool(workflow_hints),
                "memory_hints": len(memory_hints),
                "mission_runtime_read_only": True,
                "reasoning_engine": reasoning_result is not None,
            },
            expanded=expand,
        )
        logger.info(
            "Long-term plan created: domain=%s projects=%d tasks=%d confidence=%.2f",
            domain.value,
            len(plan.projects),
            len(plan.all_tasks()),
            plan.summary.confidence_score,
        )
        return plan

    def expand_goal(
        self,
        goal: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
    ) -> GoalPlan:
        """Produce a deeper GoalPlan with nested subtasks and extra milestones."""
        return self.plan_goal(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=executive_evaluation,
            expand=True,
        )

    def review_plan(self, plan: GoalPlan) -> GoalPlan:
        """Critically review a plan — add risks, adjust scores, never execute.

        Does not mutate the input; returns a new GoalPlan.
        """
        if not isinstance(plan, GoalPlan):
            raise TypeError("review_plan expects a GoalPlan")

        tasks = plan.all_tasks()
        extra_risks: list[PlanningRisk] = list(plan.risks)

        blocked = [t for t in tasks if t.status == TaskStatus.BLOCKED or t.blocked_by]
        if blocked:
            extra_risks.append(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary=f"{len(blocked)} task(s) are blocked or have blockers",
                    severity="high",
                    related_task_ids=tuple(t.id for t in blocked[:8]),
                    mitigation="Resolve blockers or resequence before starting work",
                )
            )

        orphan_deps = [
            d
            for d in plan.dependencies
            if plan.task_by_id(d.from_id) is None or plan.task_by_id(d.to_id) is None
        ]
        if orphan_deps:
            extra_risks.append(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary=f"{len(orphan_deps)} dependency edge(s) reference missing tasks",
                    severity="high",
                    mitigation="Recalculate the plan to rebuild the dependency graph",
                )
            )

        no_success = [t for t in tasks if not t.success_conditions]
        if no_success and len(no_success) > len(tasks) // 2:
            extra_risks.append(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary="Many tasks lack success conditions",
                    severity="medium",
                    related_task_ids=tuple(t.id for t in no_success[:6]),
                    mitigation="Define measurable success criteria per task",
                )
            )

        # Confidence: reward completeness, penalize unresolved risks.
        confidence = plan.summary.confidence_score
        confidence = min(0.95, confidence + 0.05)  # review itself adds clarity
        if orphan_deps:
            confidence = max(0.2, confidence - 0.2)
        if blocked:
            confidence = max(0.25, confidence - 0.1)

        high_risk_count = sum(1 for r in extra_risks if r.severity == "high")
        overall_risk = plan.summary.overall_risk
        if high_risk_count >= 2:
            overall_risk = "high"
        elif high_risk_count == 1 and overall_risk == "low":
            overall_risk = "medium"

        reasoning = (
            f"Reviewed plan for « {plan.goal} »: {len(tasks)} tasks, "
            f"{len(extra_risks)} risk(s), {len(plan.dependencies)} dependencies. "
            f"{plan.summary.reasoning_summary}"
        )
        summary = PlanningSummary(
            confidence_score=round(confidence, 3),
            complexity_score=plan.summary.complexity_score,
            estimated_implementation_time=plan.summary.estimated_implementation_time,
            reasoning_summary=reasoning.strip(),
            overall_risk=overall_risk,
            critical_path_task_ids=plan.summary.critical_path_task_ids,
            parallel_groups=plan.summary.parallel_groups,
            sequential_task_ids=plan.summary.sequential_task_ids,
            quick_wins=plan.summary.quick_wins,
            high_risk_tasks=plan.summary.high_risk_tasks,
            low_risk_tasks=plan.summary.low_risk_tasks,
            research_tasks=plan.summary.research_tasks,
            implementation_tasks=plan.summary.implementation_tasks,
            testing_tasks=plan.summary.testing_tasks,
            documentation_tasks=plan.summary.documentation_tasks,
            deployment_tasks=plan.summary.deployment_tasks,
        )

        # Refresh executive recommendation without changing task structure.
        recommendations = plan.recommendations
        if self._executive_function is not None:
            exec_rec = self._executive_function.recommend_next_from_goal_plan(plan)
            recommendations = (exec_rec, *tuple(
                r for r in plan.recommendations if r.source != "executive_function"
            ))

        return GoalPlan(
            goal=plan.goal,
            projects=plan.projects,
            dependencies=plan.dependencies,
            risks=tuple(extra_risks),
            recommendations=recommendations,
            summary=summary,
            success_criteria=plan.success_criteria,
            required_tools=plan.required_tools,
            context_summary=plan.context_summary,
            mission_proposals=plan.mission_proposals,
            domain=plan.domain,
            request=plan.request,
            sources={**plan.sources, "reviewed": True},
            expanded=plan.expanded,
        )

    def recalculate_plan(
        self,
        plan: GoalPlan,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
    ) -> GoalPlan:
        """Rebuild a plan from its goal using fresh workspace / project context."""
        if not isinstance(plan, GoalPlan):
            raise TypeError("recalculate_plan expects a GoalPlan")
        goal_text = plan.request or plan.goal
        rebuilt = self.plan_goal(
            goal_text,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=executive_evaluation,
            expand=plan.expanded,
        )
        return GoalPlan(
            goal=rebuilt.goal,
            projects=rebuilt.projects,
            dependencies=rebuilt.dependencies,
            risks=rebuilt.risks,
            recommendations=rebuilt.recommendations,
            summary=rebuilt.summary,
            success_criteria=rebuilt.success_criteria,
            required_tools=rebuilt.required_tools,
            context_summary=rebuilt.context_summary,
            mission_proposals=rebuilt.mission_proposals,
            domain=rebuilt.domain,
            request=rebuilt.request,
            sources={**rebuilt.sources, "recalculated_from": plan.goal},
            expanded=rebuilt.expanded,
        )

    # --- Context resolution ---

    def _resolve_user(self) -> str | None:
        if self._context_manager is None:
            return None
        return getattr(self._context_manager, "current_user", None)

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is None:
            return None
        return getattr(self._context_manager, "active_project", None) or None

    def _resolve_workspace(
        self,
        workspace: WorkspaceSnapshot | None,
        *,
        user: str | None,
        project_id: str | None,
    ) -> WorkspaceSnapshot | None:
        if workspace is not None:
            return workspace
        if self._workspace_awareness is None:
            return None
        return self._workspace_awareness.refresh(user=user, project_id=project_id)

    def _resolve_executive(
        self,
        evaluation: ExecutiveEvaluation | None,
        message: str,
        *,
        user: str | None,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
    ) -> ExecutiveEvaluation | None:
        if evaluation is not None:
            return evaluation
        if self._executive_function is None:
            return None
        return self._executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def _analyze_architecture(
        self,
        *,
        user: str | None,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        executive_evaluation: ExecutiveEvaluation | None,
    ) -> ArchitectureSummary | None:
        if self._project_intelligence is None:
            return None
        return self._project_intelligence.analyze_project(
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=executive_evaluation,
            refresh=False,
        )

    def _retrieve_memory(
        self,
        message: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> tuple[str, ...]:
        if self._memory_service is None or not message:
            return ()
        try:
            result = self._memory_service.retrieve(
                user or "Nolan",
                message,
                project_id=project_id,
            )
        except Exception:  # noqa: BLE001 — planning must not fail on memory
            logger.debug("Memory retrieval failed during long-term planning", exc_info=True)
            return ()
        hints: list[str] = []
        notes = getattr(result, "notes", None) or getattr(result, "items", None) or ()
        for note in notes:
            text = getattr(note, "content", None) or getattr(note, "text", None) or str(note)
            if text:
                hints.append(str(text)[:200])
            if len(hints) >= 5:
                break
        return tuple(hints)

    def _workflow_quality_gates(self, request: str) -> tuple[str, ...]:
        """Reuse Developer Workflow guidance: docs → tests → validation → review."""
        gates = (
            "Document the objective and success criteria before implementation",
            "Write or identify tests before coding the core change",
            "Validate against workspace constraints and existing modules",
            "Review the plan and risk list before starting implementation",
        )
        if self._developer_workflow is None:
            return gates
        try:
            # Advisory only — we do not execute the workflow plan.
            wf = self._developer_workflow.plan(f"Prepare sprint for: {request}")
            extras: list[str] = []
            for item in getattr(wf, "documentation_updates", ())[:3]:
                extras.append(f"Documentation: {item}")
            for item in getattr(wf, "test_plan", ())[:3]:
                extras.append(f"Test: {item}")
            return gates + tuple(extras)
        except Exception:  # noqa: BLE001
            logger.debug("Developer workflow hints failed", exc_info=True)
            return gates

    # --- Domain & decomposition ---

    def _classify_domain(self, request: str) -> GoalDomain:
        lowered = request.lower()
        scores: dict[GoalDomain, int] = {d: 0 for d in GoalDomain}
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in lowered:
                    scores[domain] += 1
        best = max(scores, key=lambda d: scores[d])
        if scores[best] == 0:
            return GoalDomain.GENERAL
        # Automate + trading → trading; automate alone → automation.
        if scores[GoalDomain.TRADING] > 0 and (
            "automate" in lowered or scores[GoalDomain.AUTOMATION] > 0
        ):
            return GoalDomain.TRADING
        return best

    def _normalize_goal(self, request: str) -> str:
        text = request.strip()
        if text.endswith("."):
            text = text[:-1]
        if not text:
            return "Untitled goal"
        return text[0].upper() + text[1:]

    def _decompose_into_projects(
        self,
        request: str,
        domain: GoalDomain,
        *,
        expand: bool,
    ) -> list[dict[str, Any]]:
        """Return project specs (title, description, focus keywords)."""
        tokens = self._goal_tokens(request)
        label = self._short_label(request, tokens)

        if domain == GoalDomain.TRADING:
            specs = [
                {
                    "title": f"{label} — Research & Strategy Spec",
                    "description": (
                        f"Clarify the trading objective « {request} », "
                        "rules, risk limits, and success metrics."
                    ),
                    "focus": "research",
                },
                {
                    "title": f"{label} — Execution & Broker Integration",
                    "description": (
                        "Wire paper/live broker paths, signals, and safety gates "
                        "without enabling live trading by default."
                    ),
                    "focus": "integration",
                },
                {
                    "title": f"{label} — Validation & Monitoring",
                    "description": (
                        "Backtests, paper validation, monitoring, and documentation "
                        "before any live enablement."
                    ),
                    "focus": "validation",
                },
            ]
        elif domain == GoalDomain.AUTOMATION:
            specs = [
                {
                    "title": f"{label} — Process Discovery",
                    "description": f"Map the manual process behind « {request} ».",
                    "focus": "research",
                },
                {
                    "title": f"{label} — Automation Implementation",
                    "description": "Build the automation pipeline with tools and permissions.",
                    "focus": "implementation",
                },
                {
                    "title": f"{label} — Hardening & Ops",
                    "description": "Tests, docs, scheduling, and failure handling.",
                    "focus": "validation",
                },
            ]
        elif domain == GoalDomain.INTEGRATION:
            specs = [
                {
                    "title": f"{label} — Integration Design",
                    "description": f"Design the integration for « {request} ».",
                    "focus": "architecture",
                },
                {
                    "title": f"{label} — Connector Implementation",
                    "description": "Implement connectors, auth, and error handling.",
                    "focus": "implementation",
                },
                {
                    "title": f"{label} — Verification",
                    "description": "End-to-end tests, docs, and permission review.",
                    "focus": "validation",
                },
            ]
        elif expand or self._is_large_goal(request):
            specs = [
                {
                    "title": f"{label} — Discovery",
                    "description": f"Scope and constraints for « {request} ».",
                    "focus": "research",
                },
                {
                    "title": f"{label} — Core Delivery",
                    "description": "Primary implementation workstream.",
                    "focus": "implementation",
                },
                {
                    "title": f"{label} — Quality & Launch",
                    "description": "Tests, documentation, review, and rollout.",
                    "focus": "validation",
                },
            ]
        else:
            specs = [
                {
                    "title": f"{label}",
                    "description": f"Deliver « {request} » as a single coordinated project.",
                    "focus": "implementation",
                },
            ]
        return specs

    def _is_large_goal(self, request: str) -> bool:
        lowered = request.lower()
        if len(request) > 80:
            return True
        multi_signals = (
            " and ",
            " then ",
            " plus ",
            " including ",
            "automate",
            "end-to-end",
            "full",
            "complete",
            "system",
            "platform",
        )
        return sum(1 for s in multi_signals if s in lowered) >= 2

    def _goal_tokens(self, request: str) -> tuple[str, ...]:
        tokens = [
            t.lower()
            for t in _TOKEN_RE.findall(request)
            if t.lower() not in _STOPWORDS
        ]
        return tuple(dict.fromkeys(tokens))

    def _short_label(self, request: str, tokens: tuple[str, ...]) -> str:
        if tokens:
            return " ".join(t.capitalize() for t in tokens[:4])
        return request[:48].strip() or "Goal"

    def _build_project_plan(
        self,
        spec: dict[str, Any],
        *,
        request: str,
        domain: GoalDomain,
        architecture: ArchitectureSummary | None,
        snapshot: WorkspaceSnapshot | None,
        evaluation: ExecutiveEvaluation | None,
        expand: bool,
        workflow_hints: tuple[str, ...],
    ) -> ProjectPlan:
        project_id = _new_id("proj")
        existing, missing, conflicts, duplicates = self._project_intelligence_signals(
            request,
            architecture,
            snapshot,
            evaluation,
        )
        milestones = self._build_milestones(
            project_id=project_id,
            request=request,
            domain=domain,
            focus=str(spec.get("focus", "implementation")),
            expand=expand,
            workflow_hints=workflow_hints,
            existing_features=existing,
            missing_systems=missing,
        )
        duration = self._estimate_project_duration(milestones)
        return ProjectPlan(
            id=project_id,
            title=str(spec["title"]),
            description=str(spec["description"]),
            milestones=milestones,
            existing_features=existing,
            missing_systems=missing,
            architecture_conflicts=conflicts,
            duplicate_work_warnings=duplicates,
            estimated_duration=duration,
            priority=(
                TaskPriority.HIGH
                if domain in (GoalDomain.TRADING, GoalDomain.INFRASTRUCTURE)
                else TaskPriority.NORMAL
            ),
        )

    def _project_intelligence_signals(
        self,
        request: str,
        architecture: ArchitectureSummary | None,
        snapshot: WorkspaceSnapshot | None,
        evaluation: ExecutiveEvaluation | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        existing: list[str] = []
        missing: list[str] = []
        conflicts: list[str] = []
        duplicates: list[str] = []

        if self._project_intelligence is not None:
            for token in self._goal_tokens(request)[:6]:
                try:
                    loc = self._project_intelligence.find_feature(token)
                except Exception:  # noqa: BLE001
                    continue
                name = getattr(loc, "feature", None) or token
                confidence = float(getattr(loc, "confidence", 0.0) or 0.0)
                primary = getattr(loc, "primary_files", ()) or ()
                if confidence >= 0.5 and primary:
                    existing.append(str(name))
                elif confidence < 0.3:
                    missing.append(str(name))

        if architecture is not None:
            modules = {m.name.lower() for m in architecture.modules}
            # Known Titan gaps that planning should surface when relevant.
            known_gaps = ("prompts", "voice", "trading execution")
            for gap in known_gaps:
                if gap.replace(" ", "_") not in modules and gap.split()[0] in request.lower():
                    missing.append(gap)
            for violation in architecture.dependency_graph.boundary_violations[:5]:
                conflicts.append(str(violation))

        if snapshot is not None:
            for rec in snapshot.recommendations[:5]:
                kind = getattr(rec, "kind", "")
                if kind in ("missing_documentation", "documentation_changed"):
                    missing.append(getattr(rec, "summary", str(rec)))
            for mission in snapshot.active_missions[:8]:
                title = str(mission.get("title", ""))
                objective = str(mission.get("objective", ""))
                if self._token_overlap(request, f"{title} {objective}") >= 0.35:
                    duplicates.append(
                        f"Active mission may overlap: « {title or objective[:60]} »"
                    )

        if evaluation is not None:
            for ranked in evaluation.ranked_missions[:5]:
                if self._token_overlap(request, f"{ranked.title}") >= 0.4:
                    duplicates.append(
                        f"Executive-ranked mission overlap: « {ranked.title} »"
                    )

        return (
            tuple(dict.fromkeys(existing)),
            tuple(dict.fromkeys(missing)),
            tuple(dict.fromkeys(conflicts)),
            tuple(dict.fromkeys(duplicates)),
        )

    def _token_overlap(self, a: str, b: str) -> float:
        ta = set(self._goal_tokens(a))
        tb = set(self._goal_tokens(b))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / float(len(ta | tb))

    def _build_milestones(
        self,
        *,
        project_id: str,
        request: str,
        domain: GoalDomain,
        focus: str,
        expand: bool,
        workflow_hints: tuple[str, ...],
        existing_features: tuple[str, ...],
        missing_systems: tuple[str, ...],
    ) -> tuple[Milestone, ...]:
        # Quality-first order: docs/research → architecture → implement → test → review → deploy
        blueprint: list[tuple[str, str, TaskKind]] = [
            ("Discovery & documentation", "Clarify scope, constraints, and docs", TaskKind.DOCUMENTATION),
            ("Research & requirements", "Gather facts and define success criteria", TaskKind.RESEARCH),
            ("Architecture & design", "Design modules and interfaces", TaskKind.ARCHITECTURE),
            ("Implementation", "Build the core capability", TaskKind.IMPLEMENTATION),
            ("Testing & validation", "Prove correctness with tests and checks", TaskKind.TESTING),
            ("Review", "Human/peer review before merge or enablement", TaskKind.REVIEW),
        ]
        if domain in (GoalDomain.TRADING, GoalDomain.INFRASTRUCTURE, GoalDomain.AUTOMATION):
            blueprint.append(
                ("Deployment readiness", "Rollout checklist — paper/default-safe", TaskKind.DEPLOYMENT)
            )

        if focus == "research":
            blueprint = blueprint[:3]
        elif focus == "validation":
            blueprint = [
                ("Validation plan", "Define validation gates", TaskKind.VALIDATION),
                ("Testing & validation", "Execute test and validation plan", TaskKind.TESTING),
                ("Documentation", "Record outcomes and runbooks", TaskKind.DOCUMENTATION),
                ("Review", "Sign-off review", TaskKind.REVIEW),
            ]
        elif focus == "architecture":
            blueprint = blueprint[:4]
        elif not expand and focus == "implementation":
            # Compact single-project path still keeps quality gates first.
            blueprint = [
                ("Prep: docs & tests", "Documentation and test plan before coding", TaskKind.DOCUMENTATION),
                ("Implementation", "Build the core capability", TaskKind.IMPLEMENTATION),
                ("Testing & review", "Tests, validation, and review", TaskKind.TESTING),
            ]

        milestones: list[Milestone] = []
        prev_id: str | None = None
        for order, (title, description, kind) in enumerate(blueprint):
            mid = _new_id("ms")
            tasks = self._build_tasks_for_milestone(
                milestone_id=mid,
                request=request,
                kind=kind,
                expand=expand,
                workflow_hints=workflow_hints,
                existing_features=existing_features,
                missing_systems=missing_systems,
                domain=domain,
            )
            deps = (prev_id,) if prev_id else ()
            milestones.append(
                Milestone(
                    id=mid,
                    title=title,
                    description=description,
                    tasks=tasks,
                    success_criteria=self._milestone_success(kind, request),
                    estimated_duration=self._estimate_milestone_duration(tasks),
                    order=order,
                    dependencies=deps,
                )
            )
            prev_id = mid
        # Silence unused project_id for future cross-project linking.
        _ = project_id
        return tuple(milestones)

    def _build_tasks_for_milestone(
        self,
        *,
        milestone_id: str,
        request: str,
        kind: TaskKind,
        expand: bool,
        workflow_hints: tuple[str, ...],
        existing_features: tuple[str, ...],
        missing_systems: tuple[str, ...],
        domain: GoalDomain,
    ) -> tuple[Task, ...]:
        _ = milestone_id
        templates = self._task_templates(
            kind=kind,
            request=request,
            domain=domain,
            existing_features=existing_features,
            missing_systems=missing_systems,
            workflow_hints=workflow_hints,
        )
        tasks: list[Task] = []
        prev: str | None = None
        for index, tmpl in enumerate(templates):
            tid = _new_id("task")
            subtasks: tuple[SubTask, ...] = ()
            if expand:
                subtasks = tuple(
                    SubTask(
                        id=_new_id("sub"),
                        title=st_title,
                        description=st_desc,
                        estimated_duration=st_dur,
                        required_tools=tmpl.get("tools", ()),
                    )
                    for st_title, st_desc, st_dur in tmpl.get("subtasks", ())
                )
            deps = (prev,) if prev and not tmpl.get("parallel_safe") else ()
            blocked = ()
            status = TaskStatus.READY if prev is None and index == 0 else TaskStatus.PENDING
            if tmpl.get("blocked"):
                status = TaskStatus.BLOCKED
                blocked = deps

            difficulty = TaskDifficulty(tmpl.get("difficulty", TaskDifficulty.MEDIUM.value))
            priority = TaskPriority(tmpl.get("priority", TaskPriority.NORMAL.value))
            high_risk = bool(tmpl.get("high_risk")) or difficulty in (
                TaskDifficulty.HARD,
                TaskDifficulty.EXPERT,
            )
            low_risk = bool(tmpl.get("low_risk")) or difficulty in (
                TaskDifficulty.TRIVIAL,
                TaskDifficulty.EASY,
            )
            quick_win = bool(tmpl.get("quick_win")) or (
                low_risk and kind in (TaskKind.DOCUMENTATION, TaskKind.RESEARCH)
            )

            task = Task(
                id=tid,
                title=str(tmpl["title"]),
                description=str(tmpl["description"]),
                priority=priority,
                difficulty=difficulty,
                estimated_duration=str(tmpl.get("duration", "4h")),
                dependencies=deps,
                required_tools=tuple(tmpl.get("tools", ())),
                success_conditions=tuple(tmpl.get("success", ())),
                blocked_by=blocked,
                status=status,
                kind=kind,
                subtasks=subtasks,
                is_parallel_safe=bool(tmpl.get("parallel_safe")),
                is_quick_win=quick_win,
                is_high_risk=high_risk,
                is_low_risk=low_risk and not high_risk,
            )
            tasks.append(task)
            if not task.is_parallel_safe:
                prev = tid
        return tuple(tasks)

    def _task_templates(
        self,
        *,
        kind: TaskKind,
        request: str,
        domain: GoalDomain,
        existing_features: tuple[str, ...],
        missing_systems: tuple[str, ...],
        workflow_hints: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        label = request[:80]
        existing_note = (
            f"Reuse existing: {', '.join(existing_features[:4])}."
            if existing_features
            else "Inventory related modules first."
        )
        missing_note = (
            f"Missing systems to account for: {', '.join(missing_systems[:4])}."
            if missing_systems
            else "Confirm no critical subsystem is missing."
        )

        if kind == TaskKind.DOCUMENTATION:
            return [
                {
                    "title": "Capture objective & success criteria",
                    "description": f"Write down the goal « {label} » and measurable outcomes. {workflow_hints[0] if workflow_hints else ''}",
                    "duration": "1h",
                    "difficulty": TaskDifficulty.EASY.value,
                    "priority": TaskPriority.HIGH.value,
                    "tools": ("obsidian",),
                    "success": ("Written success criteria exist", "Scope boundaries documented"),
                    "parallel_safe": True,
                    "quick_win": True,
                    "low_risk": True,
                    "subtasks": (
                        ("Draft goal statement", "One-paragraph objective", "20m"),
                        ("List non-goals", "Explicit out-of-scope items", "20m"),
                        ("Define done", "Measurable success checks", "20m"),
                    ),
                },
                {
                    "title": "Update architecture / changelog notes",
                    "description": "Plan documentation updates (ARCHITECTURE, CHANGELOG) — do not write yet.",
                    "duration": "1h",
                    "difficulty": TaskDifficulty.EASY.value,
                    "tools": ("obsidian",),
                    "success": ("Doc update checklist prepared",),
                    "parallel_safe": True,
                    "quick_win": True,
                    "low_risk": True,
                    "subtasks": (
                        ("List docs to touch", "ARCHITECTURE / feature docs", "15m"),
                        ("Note version bump", "Semver expectation", "10m"),
                    ),
                },
            ]

        if kind == TaskKind.RESEARCH:
            tools = ("browser", "web_search", "obsidian")
            if domain == GoalDomain.TRADING:
                tools = ("browser", "web_search", "trading", "obsidian")
            return [
                {
                    "title": "Research requirements & constraints",
                    "description": f"Investigate « {label} ». {existing_note} {missing_note}",
                    "duration": "4h",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "tools": tools,
                    "success": ("Requirements list written", "Constraints and risks noted"),
                    "parallel_safe": False,
                    "subtasks": (
                        ("Survey existing code", existing_note, "1h"),
                        ("External research", "Docs / APIs / prior art", "2h"),
                        ("Constraint list", "Permissions, risk, data", "1h"),
                    ),
                },
                {
                    "title": "Identify blockers & dependencies",
                    "description": "List external dependencies, credentials, and policy blockers.",
                    "duration": "2h",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "tools": tools,
                    "success": ("Blocker list exists", "Owners identified"),
                    "parallel_safe": True,
                    "low_risk": True,
                    "subtasks": (
                        ("Credential needs", "Keys / accounts required", "30m"),
                        ("Policy checks", "LIVE vs PAPER defaults", "30m"),
                    ),
                },
            ]

        if kind == TaskKind.ARCHITECTURE:
            return [
                {
                    "title": "Design module boundaries",
                    "description": (
                        f"Propose architecture for « {label} » using Project Intelligence. "
                        f"{existing_note}"
                    ),
                    "duration": "4h",
                    "difficulty": TaskDifficulty.HARD.value,
                    "priority": TaskPriority.HIGH.value,
                    "tools": (),
                    "success": ("Module map agreed", "No new duplicate subsystem proposed"),
                    "high_risk": True,
                    "subtasks": (
                        ("Map existing features", existing_note, "1h"),
                        ("Propose interfaces", "Public APIs / data flow", "2h"),
                        ("Conflict check", missing_note, "1h"),
                    ),
                },
                {
                    "title": "Plan tool & permission surface",
                    "description": "List required tools and permission levels (AUTO / CONFIRM / BLOCK).",
                    "duration": "2h",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "tools": (),
                    "success": ("Tool list approved", "Risky actions flagged CONFIRM"),
                    "parallel_safe": True,
                    "subtasks": (
                        ("Enumerate tools", "terminal / python / broker / …", "45m"),
                        ("Permission matrix", "Per-action levels", "45m"),
                    ),
                },
            ]

        if kind == TaskKind.IMPLEMENTATION:
            tools = self._default_impl_tools(domain)
            return [
                {
                    "title": "Implement core capability",
                    "description": f"Build the primary path for « {label} ». {existing_note}",
                    "duration": "2d",
                    "difficulty": (
                        TaskDifficulty.HARD.value
                        if domain in (GoalDomain.TRADING, GoalDomain.INFRASTRUCTURE)
                        else TaskDifficulty.MEDIUM.value
                    ),
                    "priority": TaskPriority.HIGH.value,
                    "tools": tools,
                    "success": ("Core path works in safe/default mode", "No unauthorized LIVE actions"),
                    "high_risk": domain == GoalDomain.TRADING,
                    "subtasks": (
                        ("Scaffold modules", "Files and wiring only", "4h"),
                        ("Core logic", "Happy path", "1d"),
                        ("Error handling", "Fail-safe defaults", "4h"),
                    ),
                },
                {
                    "title": "Wire Brain / Mission facades (if needed)",
                    "description": "Expose plan-only or runtime APIs without duplicating existing engines.",
                    "duration": "4h",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "tools": tools,
                    "success": ("Brain API documented", "No duplicate Brain/runtime"),
                    "parallel_safe": True,
                    "subtasks": (
                        ("API sketch", "Method signatures", "1h"),
                        ("Composition wiring", "Inject shared instances", "2h"),
                    ),
                },
            ]

        if kind in (TaskKind.TESTING, TaskKind.VALIDATION):
            return [
                {
                    "title": "Author / extend automated tests",
                    "description": (
                        f"Cover « {label} » with unit and integration tests. "
                        f"{workflow_hints[1] if len(workflow_hints) > 1 else ''}"
                    ),
                    "duration": "1d",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "priority": TaskPriority.HIGH.value,
                    "tools": ("python", "terminal"),
                    "success": ("Tests written", "Critical paths covered"),
                    "subtasks": (
                        ("Unit tests", "Pure logic", "4h"),
                        ("Integration tests", "Brain / mission facades", "4h"),
                    ),
                },
                {
                    "title": "Validate against workspace constraints",
                    "description": f"{missing_note} Confirm plan remains feasible.",
                    "duration": "4h",
                    "difficulty": TaskDifficulty.MEDIUM.value,
                    "tools": ("terminal", "python"),
                    "success": ("Validation checklist passed", "Impossible work removed"),
                    "parallel_safe": True,
                    "low_risk": True,
                    "subtasks": (
                        ("Run targeted pytest", "Related suites only", "2h"),
                        ("Manual checklist", "Permissions / safety", "2h"),
                    ),
                },
            ]

        if kind == TaskKind.REVIEW:
            return [
                {
                    "title": "Plan review & risk sign-off",
                    "description": "Review implementation against success criteria and risks.",
                    "duration": "2h",
                    "difficulty": TaskDifficulty.EASY.value,
                    "tools": (),
                    "success": ("Review notes captured", "Open risks accepted or mitigated"),
                    "quick_win": True,
                    "low_risk": True,
                    "parallel_safe": True,
                    "subtasks": (
                        ("Diff review", "Scope vs plan", "1h"),
                        ("Risk acceptance", "Document residual risk", "30m"),
                    ),
                },
            ]

        if kind == TaskKind.DEPLOYMENT:
            return [
                {
                    "title": "Deployment / enablement checklist",
                    "description": (
                        "Prepare safe rollout (paper/default). Never enable LIVE trading "
                        "or destructive actions without explicit confirmation."
                    ),
                    "duration": "4h",
                    "difficulty": TaskDifficulty.HARD.value,
                    "priority": TaskPriority.CRITICAL.value,
                    "tools": ("terminal",),
                    "success": ("Checklist complete", "LIVE remains opt-in"),
                    "high_risk": True,
                    "subtasks": (
                        ("Env checklist", "Flags and secrets", "1h"),
                        ("Rollback plan", "How to disable", "1h"),
                        ("Monitoring hooks", "Health signals", "2h"),
                    ),
                },
            ]

        return [
            {
                "title": f"Work on {kind.value}",
                "description": f"Advance « {label} » ({kind.value}).",
                "duration": "4h",
                "tools": (),
                "success": ("Step completed",),
            }
        ]

    def _default_impl_tools(self, domain: GoalDomain) -> tuple[str, ...]:
        if domain == GoalDomain.TRADING:
            return ("python", "terminal", "trading", "browser")
        if domain == GoalDomain.INTEGRATION:
            return ("python", "terminal", "github", "browser")
        if domain == GoalDomain.AUTOMATION:
            return ("python", "terminal", "browser", "obsidian")
        return ("python", "terminal")

    def _milestone_success(self, kind: TaskKind, request: str) -> tuple[str, ...]:
        return (
            f"{kind.value.capitalize()} milestone for « {request[:60]} » is complete",
            "Outputs reviewed; no execution performed by the planner",
        )

    # --- Graph annotation ---

    def _collect_dependencies(self, projects: tuple[ProjectPlan, ...]) -> tuple[Dependency, ...]:
        deps: list[Dependency] = []
        for project in projects:
            prev_ms: str | None = None
            for milestone in project.milestones:
                if prev_ms is not None:
                    # Milestone-level soft dependency encoded via first tasks.
                    first_tasks = milestone.tasks
                    prev_milestone = next(
                        (m for m in project.milestones if m.id == prev_ms),
                        None,
                    )
                    if prev_milestone and prev_milestone.tasks and first_tasks:
                        deps.append(
                            Dependency(
                                from_id=prev_milestone.tasks[-1].id,
                                to_id=first_tasks[0].id,
                                reason="milestone sequence",
                            )
                        )
                for task in milestone.tasks:
                    for dep_id in task.dependencies:
                        deps.append(
                            Dependency(
                                from_id=dep_id,
                                to_id=task.id,
                                reason="task dependency",
                            )
                        )
                prev_ms = milestone.id
        # Deduplicate
        seen: set[tuple[str, str]] = set()
        unique: list[Dependency] = []
        for dep in deps:
            key = (dep.from_id, dep.to_id)
            if key not in seen:
                seen.add(key)
                unique.append(dep)
        return tuple(unique)

    def _annotate_graph(
        self,
        projects: tuple[ProjectPlan, ...],
        dependencies: tuple[Dependency, ...],
    ) -> tuple[tuple[ProjectPlan, ...], tuple[str, ...], tuple[tuple[str, ...], ...]]:
        """Mark critical path, blocked status, and parallel groups."""
        task_map: dict[str, Task] = {}
        for project in projects:
            for milestone in project.milestones:
                for task in milestone.tasks:
                    task_map[task.id] = task

        successors: dict[str, list[str]] = {tid: [] for tid in task_map}
        predecessors: dict[str, list[str]] = {tid: [] for tid in task_map}
        for dep in dependencies:
            if dep.from_id in task_map and dep.to_id in task_map:
                successors[dep.from_id].append(dep.to_id)
                predecessors[dep.to_id].append(dep.from_id)

        # Longest path (by simple hop count + difficulty weight) as critical path.
        weight = {
            TaskDifficulty.TRIVIAL: 1,
            TaskDifficulty.EASY: 2,
            TaskDifficulty.MEDIUM: 3,
            TaskDifficulty.HARD: 5,
            TaskDifficulty.EXPERT: 8,
        }
        memo: dict[str, int] = {}

        def longest(tid: str) -> int:
            if tid in memo:
                return memo[tid]
            kids = successors.get(tid, [])
            if not kids:
                memo[tid] = weight.get(task_map[tid].difficulty, 3)
                return memo[tid]
            memo[tid] = weight.get(task_map[tid].difficulty, 3) + max(
                longest(k) for k in kids
            )
            return memo[tid]

        for tid in task_map:
            longest(tid)

        roots = [tid for tid, preds in predecessors.items() if not preds]
        critical: list[str] = []
        if roots:
            cursor = max(roots, key=lambda t: memo.get(t, 0))
            critical.append(cursor)
            while successors.get(cursor):
                cursor = max(successors[cursor], key=lambda t: memo.get(t, 0))
                critical.append(cursor)

        critical_set = set(critical)

        # Parallel groups: tasks that share the same predecessor set and are parallel_safe.
        parallel_groups: list[tuple[str, ...]] = []
        by_pred: dict[tuple[str, ...], list[str]] = {}
        for tid, preds in predecessors.items():
            key = tuple(sorted(preds))
            by_pred.setdefault(key, []).append(tid)
        for group in by_pred.values():
            safe = [tid for tid in group if task_map[tid].is_parallel_safe or len(group) > 1]
            if len(safe) >= 2:
                parallel_groups.append(tuple(safe))

        annotated_projects: list[ProjectPlan] = []
        for project in projects:
            new_milestones: list[Milestone] = []
            for milestone in project.milestones:
                new_tasks: list[Task] = []
                for task in milestone.tasks:
                    preds = tuple(predecessors.get(task.id, ()))
                    blocked_by = preds
                    status = task.status
                    if preds and status == TaskStatus.READY:
                        status = TaskStatus.PENDING
                    if task.blocked_by or (
                        preds and any(
                            task_map[p].status
                            not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
                            for p in preds
                            if p in task_map
                        )
                        and task.status == TaskStatus.BLOCKED
                    ):
                        status = TaskStatus.BLOCKED
                        blocked_by = preds
                    # First tasks with no preds stay READY.
                    if not preds and status == TaskStatus.PENDING:
                        status = TaskStatus.READY

                    new_tasks.append(
                        Task(
                            id=task.id,
                            title=task.title,
                            description=task.description,
                            priority=task.priority,
                            difficulty=task.difficulty,
                            estimated_duration=task.estimated_duration,
                            dependencies=preds or task.dependencies,
                            required_tools=task.required_tools,
                            success_conditions=task.success_conditions,
                            blocked_by=blocked_by if status == TaskStatus.BLOCKED else (),
                            status=status,
                            kind=task.kind,
                            subtasks=task.subtasks,
                            is_parallel_safe=task.is_parallel_safe,
                            is_critical_path=task.id in critical_set,
                            is_quick_win=task.is_quick_win,
                            is_high_risk=task.is_high_risk,
                            is_low_risk=task.is_low_risk,
                        )
                    )
                new_milestones.append(
                    Milestone(
                        id=milestone.id,
                        title=milestone.title,
                        description=milestone.description,
                        tasks=tuple(new_tasks),
                        success_criteria=milestone.success_criteria,
                        estimated_duration=milestone.estimated_duration,
                        order=milestone.order,
                        dependencies=milestone.dependencies,
                    )
                )
            annotated_projects.append(
                ProjectPlan(
                    id=project.id,
                    title=project.title,
                    description=project.description,
                    milestones=tuple(new_milestones),
                    existing_features=project.existing_features,
                    missing_systems=project.missing_systems,
                    architecture_conflicts=project.architecture_conflicts,
                    duplicate_work_warnings=project.duplicate_work_warnings,
                    estimated_duration=project.estimated_duration,
                    priority=project.priority,
                )
            )

        return tuple(annotated_projects), tuple(critical), tuple(parallel_groups)

    # --- Risks, summary, recommendations ---

    def _identify_risks(
        self,
        projects: tuple[ProjectPlan, ...],
        architecture: ArchitectureSummary | None,
        snapshot: WorkspaceSnapshot | None,
    ) -> tuple[PlanningRisk, ...]:
        risks: list[PlanningRisk] = []
        for project in projects:
            for warning in project.duplicate_work_warnings:
                risks.append(
                    PlanningRisk(
                        id=_new_id("risk"),
                        summary=warning,
                        severity="medium",
                        mitigation="Align with existing mission or cancel duplicate scope",
                    )
                )
            for conflict in project.architecture_conflicts:
                risks.append(
                    PlanningRisk(
                        id=_new_id("risk"),
                        summary=f"Architecture conflict: {conflict}",
                        severity="high",
                        mitigation="Resolve boundary violation before implementation",
                    )
                )
            for missing in project.missing_systems[:4]:
                risks.append(
                    PlanningRisk(
                        id=_new_id("risk"),
                        summary=f"Missing system may block delivery: {missing}",
                        severity="medium",
                        mitigation="Add prerequisite project or reduce scope",
                    )
                )
            for milestone in project.milestones:
                for task in milestone.tasks:
                    if task.is_high_risk:
                        risks.append(
                            PlanningRisk(
                                id=_new_id("risk"),
                                summary=f"High-risk task: {task.title}",
                                severity="high",
                                related_task_ids=(task.id,),
                                mitigation="Require confirmation; prefer paper/safe defaults",
                            )
                        )

        if snapshot is not None and not snapshot.documentation_files:
            risks.append(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary="Workspace has little/no documentation — planning confidence reduced",
                    severity="low",
                    mitigation="Add docs before large implementation",
                )
            )
        if architecture is None:
            risks.append(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary="Project Intelligence unavailable — architecture signals missing",
                    severity="low",
                    mitigation="Re-run with Project Intelligence wired",
                )
            )
        # Deduplicate by summary
        seen: set[str] = set()
        unique: list[PlanningRisk] = []
        for risk in risks:
            if risk.summary in seen:
                continue
            seen.add(risk.summary)
            unique.append(risk)
        return tuple(unique[:20])

    def _build_summary(
        self,
        projects: tuple[ProjectPlan, ...],
        dependencies: tuple[Dependency, ...],
        critical_ids: tuple[str, ...],
        parallel_groups: tuple[tuple[str, ...], ...],
        risks: tuple[PlanningRisk, ...],
        *,
        domain: GoalDomain,
        expand: bool,
        architecture: ArchitectureSummary | None,
        snapshot: WorkspaceSnapshot | None,
    ) -> PlanningSummary:
        tasks = [t for p in projects for m in p.milestones for t in m.tasks]
        by_kind: dict[TaskKind, list[str]] = {k: [] for k in TaskKind}
        quick: list[str] = []
        high: list[str] = []
        low: list[str] = []
        sequential: list[str] = []
        for task in tasks:
            by_kind[task.kind].append(task.id)
            if task.is_quick_win:
                quick.append(task.id)
            if task.is_high_risk:
                high.append(task.id)
            if task.is_low_risk:
                low.append(task.id)
            if task.dependencies and not task.is_parallel_safe:
                sequential.append(task.id)

        complexity = self._complexity_score(tasks, dependencies, domain, expand)
        confidence = self._confidence_score(
            tasks,
            risks,
            architecture=architecture,
            snapshot=snapshot,
            expand=expand,
        )
        overall = "low"
        if any(r.severity == "high" for r in risks) or complexity >= 0.7:
            overall = "high"
        elif any(r.severity == "medium" for r in risks) or complexity >= 0.4:
            overall = "medium"

        est = self._estimate_total_duration(tasks, critical_ids)
        reasoning = (
            f"Domain={domain.value}; {len(projects)} project(s); {len(tasks)} task(s); "
            f"{len(dependencies)} dependencies; critical path length={len(critical_ids)}; "
            f"parallel groups={len(parallel_groups)}. "
            "Quality gates (docs/tests/validation/review) ordered before implementation. "
            "Planner performed no execution."
        )
        return PlanningSummary(
            confidence_score=confidence,
            complexity_score=complexity,
            estimated_implementation_time=est,
            reasoning_summary=reasoning,
            overall_risk=overall,
            critical_path_task_ids=critical_ids,
            parallel_groups=parallel_groups,
            sequential_task_ids=tuple(sequential),
            quick_wins=tuple(quick),
            high_risk_tasks=tuple(high),
            low_risk_tasks=tuple(low),
            research_tasks=tuple(by_kind[TaskKind.RESEARCH]),
            implementation_tasks=tuple(by_kind[TaskKind.IMPLEMENTATION]),
            testing_tasks=tuple(by_kind[TaskKind.TESTING] + by_kind[TaskKind.VALIDATION]),
            documentation_tasks=tuple(by_kind[TaskKind.DOCUMENTATION]),
            deployment_tasks=tuple(by_kind[TaskKind.DEPLOYMENT]),
        )

    def _complexity_score(
        self,
        tasks: list[Task],
        dependencies: tuple[Dependency, ...],
        domain: GoalDomain,
        expand: bool,
    ) -> float:
        if not tasks:
            return 0.0
        base = min(1.0, len(tasks) / 24.0)
        dep_factor = min(0.3, len(dependencies) / 40.0)
        hard = sum(
            1
            for t in tasks
            if t.difficulty in (TaskDifficulty.HARD, TaskDifficulty.EXPERT)
        )
        hard_factor = min(0.3, hard / max(1, len(tasks)))
        domain_boost = 0.15 if domain in (GoalDomain.TRADING, GoalDomain.INFRASTRUCTURE) else 0.0
        expand_boost = 0.05 if expand else 0.0
        return round(min(1.0, base + dep_factor + hard_factor + domain_boost + expand_boost), 3)

    def _confidence_score(
        self,
        tasks: list[Task],
        risks: tuple[PlanningRisk, ...],
        *,
        architecture: ArchitectureSummary | None,
        snapshot: WorkspaceSnapshot | None,
        expand: bool,
    ) -> float:
        score = 0.45
        if architecture is not None:
            score += 0.15
        if snapshot is not None:
            score += 0.1
            if snapshot.detected_modules:
                score += 0.05
        if tasks:
            with_success = sum(1 for t in tasks if t.success_conditions)
            score += 0.1 * (with_success / len(tasks))
        if expand:
            score += 0.05
        high_risks = sum(1 for r in risks if r.severity == "high")
        score -= 0.05 * high_risks
        return round(min(0.95, max(0.15, score)), 3)

    def _parse_duration_hours(self, text: str) -> float:
        raw = (text or "").strip().lower()
        if not raw:
            return 4.0
        try:
            if raw.endswith("d"):
                return float(raw[:-1]) * 8.0
            if raw.endswith("h"):
                return float(raw[:-1])
            if raw.endswith("m"):
                return float(raw[:-1]) / 60.0
            return float(raw)
        except ValueError:
            return 4.0

    def _estimate_milestone_duration(self, tasks: tuple[Task, ...]) -> str:
        hours = sum(self._parse_duration_hours(t.estimated_duration) for t in tasks)
        return self._format_hours(hours)

    def _estimate_project_duration(self, milestones: tuple[Milestone, ...]) -> str:
        hours = sum(
            self._parse_duration_hours(m.estimated_duration) for m in milestones
        )
        return self._format_hours(hours)

    def _estimate_total_duration(
        self,
        tasks: list[Task],
        critical_ids: tuple[str, ...],
    ) -> str:
        by_id = {t.id: t for t in tasks}
        if critical_ids:
            hours = sum(
                self._parse_duration_hours(by_id[i].estimated_duration)
                for i in critical_ids
                if i in by_id
            )
        else:
            hours = sum(self._parse_duration_hours(t.estimated_duration) for t in tasks)
        return self._format_hours(hours)

    def _format_hours(self, hours: float) -> str:
        if hours < 8:
            return f"{int(round(hours))}h"
        days = hours / 8.0
        if days < 10:
            return f"{days:.1f}d"
        weeks = days / 5.0
        return f"{weeks:.1f}w"

    def _goal_success_criteria(
        self,
        request: str,
        domain: GoalDomain,
        projects: tuple[ProjectPlan, ...],
    ) -> tuple[str, ...]:
        criteria = [
            f"Objective « {request} » is fully planned with projects, milestones, and tasks",
            "Documentation, tests, validation, and review appear before implementation work",
            "No tools executed and no missions auto-started by the planner",
        ]
        if domain == GoalDomain.TRADING:
            criteria.append("Paper/safe defaults preserved; LIVE trading remains opt-in")
        if projects:
            criteria.append(
                f"All {len(projects)} project stream(s) have measurable milestone success criteria"
            )
        return tuple(criteria)

    def _aggregate_tools(self, projects: tuple[ProjectPlan, ...]) -> tuple[str, ...]:
        tools: list[str] = []
        for project in projects:
            for milestone in project.milestones:
                for task in milestone.tasks:
                    for tool in task.required_tools:
                        if tool not in tools:
                            tools.append(tool)
        return tuple(tools)

    def _propose_missions(
        self,
        projects: tuple[ProjectPlan, ...],
    ) -> tuple[MissionProposal, ...]:
        proposals: list[MissionProposal] = []
        for project in projects:
            for milestone in project.milestones:
                steps = tuple(t.title for t in milestone.tasks)
                if not steps:
                    continue
                proposals.append(
                    MissionProposal(
                        title=f"{project.title}: {milestone.title}",
                        objective=milestone.description or project.description,
                        steps=steps,
                    priority=project.priority.value.upper(),
                    success_criteria="; ".join(milestone.success_criteria),
                    source_project_id=project.id,
                    source_milestone_id=milestone.id,
                    )
                )
        return tuple(proposals)

    def _build_context_summary(
        self,
        snapshot: WorkspaceSnapshot | None,
        evaluation: ExecutiveEvaluation | None,
        architecture: ArchitectureSummary | None,
        memory_hints: tuple[str, ...],
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> str:
        parts: list[str] = []
        if snapshot is not None:
            parts.append(
                f"workspace={snapshot.current_project} "
                f"lang={snapshot.project_language} "
                f"modules={len(snapshot.detected_modules)}"
            )
        if evaluation is not None and evaluation.recommendation.recommended_title:
            parts.append(
                f"executive_focus={evaluation.recommendation.recommended_title}"
            )
        if architecture is not None:
            parts.append(
                f"architecture={architecture.project_name} "
                f"v{architecture.version} "
                f"pkgs={len(architecture.modules)}"
            )
        if memory_hints:
            parts.append(f"memory_hints={len(memory_hints)}")
        if reasoning_result is not None:
            parts.append(
                f"reasoning={reasoning_result.summary.domain.value} "
                f"confidence={reasoning_result.summary.confidence_score:.2f} "
                f"strategy={reasoning_result.recommendation.strategy[:80]}"
            )
        return "; ".join(parts) if parts else "no external context"

    def _build_recommendations(
        self,
        projects: tuple[ProjectPlan, ...],
        critical_ids: tuple[str, ...],
        parallel_groups: tuple[tuple[str, ...], ...],
        evaluation: ExecutiveEvaluation | None,
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> tuple[PlanningRecommendation, ...]:
        tasks = [t for p in projects for m in p.milestones for t in m.tasks]
        by_id = {t.id: t for t in tasks}

        # Prefer ready quick wins, else first critical-path ready task, else first READY.
        ready = [t for t in tasks if t.status == TaskStatus.READY]
        next_task = None
        if ready:
            quick = [t for t in ready if t.is_quick_win]
            critical_ready = [t for t in ready if t.id in critical_ids]
            next_task = (quick or critical_ready or ready)[0]

        parallel: tuple[str, ...] = ()
        if next_task is not None:
            for group in parallel_groups:
                if next_task.id in group:
                    parallel = tuple(tid for tid in group if tid != next_task.id)
                    break

        avoid = tuple(
            t.id for t in tasks if t.is_high_risk and t.status != TaskStatus.READY
        )[:6]

        rationale_parts = [
            "Start with documentation/research quality gates before implementation.",
        ]
        if reasoning_result is not None:
            rationale_parts.append(
                f"Reasoning Engine recommends: {reasoning_result.recommendation.strategy} "
                f"(confidence {reasoning_result.summary.confidence_score:.2f})."
            )
        if evaluation is not None and evaluation.recommendation.recommended_title:
            rationale_parts.append(
                f"Active executive mission focus: « {evaluation.recommendation.recommended_title} » "
                "(plan does not switch missions)."
            )
        if next_task and next_task.is_critical_path:
            rationale_parts.append("Selected task lies on the critical path.")

        primary = PlanningRecommendation(
            summary=(
                f"Next: {next_task.title}"
                if next_task
                else "No ready tasks — resolve blockers first"
            ),
            next_task_id=next_task.id if next_task else None,
            next_task_title=next_task.title if next_task else None,
            rationale=" ".join(rationale_parts),
            parallel_task_ids=parallel,
            avoid_task_ids=avoid,
            source="long_term_planner",
        )

        recs: list[PlanningRecommendation] = [primary]
        if self._executive_function is not None:
            # Build a temporary plan-shaped object for EF — use lightweight GoalPlan.
            temp = GoalPlan(
                goal="temp",
                projects=projects,
                dependencies=(),
                risks=(),
                recommendations=(),
                summary=PlanningSummary(
                    confidence_score=0.0,
                    complexity_score=0.0,
                    estimated_implementation_time="",
                    reasoning_summary="",
                    overall_risk="low",
                ),
                success_criteria=(),
                required_tools=(),
            )
            exec_rec = self._executive_function.recommend_next_from_goal_plan(temp)
            recs.append(exec_rec)

        _ = by_id
        return tuple(recs)

    def _empty_plan(self, request: str) -> GoalPlan:
        summary = PlanningSummary(
            confidence_score=0.0,
            complexity_score=0.0,
            estimated_implementation_time="0h",
            reasoning_summary="Empty goal — nothing to plan.",
            overall_risk="low",
        )
        return GoalPlan(
            goal="",
            projects=(),
            dependencies=(),
            risks=(
                PlanningRisk(
                    id=_new_id("risk"),
                    summary="Empty goal provided",
                    severity="low",
                    mitigation="Provide a concrete high-level objective",
                ),
            ),
            recommendations=(
                PlanningRecommendation(
                    summary="Provide a non-empty goal to plan",
                    rationale="Planner requires an objective string",
                ),
            ),
            summary=summary,
            success_criteria=(),
            required_tools=(),
            request=request,
        )

# =====================================
# Titan World Model
# =====================================

"""World Model V1 — Titan's structured belief about the current environment.

Aggregates read-only signals from Project Intelligence, Mission Runtime,
Developer Workflow, Knowledge Learning Engine, Memory, Code Intelligence,
Executive Function, and Proactive Intelligence into a single snapshot of
what Titan believes is true right now.

Never executes tools, never mutates missions or memory, and never runs
reasoning. Representation only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from config.settings import (
    TITAN_GITHUB_ENABLED,
    TITAN_OBSIDIAN_ENABLED,
    TITAN_OBSIDIAN_VAULT_PATH,
    VERSION,
)
from core.mission_models import Mission, MissionState, Task, TaskState

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.developer_workflow import DeveloperWorkflow
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.knowledge_learning_engine import KnowledgeLearningEngine
    from brain.proactive_intelligence import ProactiveDigest, ProactiveIntelligence
    from brain.project_intelligence import ProjectIntelligence
    from brain.tool_intelligence import ToolIntelligence
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_INTEGRATION_TOOL_IDS = frozenset(
    {
        "github",
        "obsidian",
        "calendar",
        "email",
        "browser",
        "trading",
        "web_search",
        "terminal",
        "python_runtime",
    }
)


class ProjectHealthStatus(str, Enum):
    """Coarse health classification for an active project."""

    HEALTHY = "healthy"
    ATTENTION = "attention"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProjectHealth:
    """Health signals for one active project."""

    project_id: str
    status: ProjectHealthStatus
    score: float
    summary: str
    signals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status.value,
            "score": round(self.score, 3),
            "summary": self.summary,
            "signals": list(self.signals),
        }


@dataclass(frozen=True)
class TaskRecord:
    """Open or completed task derived from mission runtime."""

    task_id: str
    mission_id: str
    mission_title: str
    description: str
    state: TaskState
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "mission_title": self.mission_title,
            "description": self.description,
            "state": self.state.value,
            "order": self.order,
        }


@dataclass(frozen=True)
class ToolAvailability:
    """Installed tool metadata for the world model."""

    tool_id: str
    display_name: str
    enabled: bool
    category: str
    risk_level: str
    requires_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "category": self.category,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass(frozen=True)
class IntegrationStatus:
    """Connected or configured external integration."""

    integration_id: str
    display_name: str
    connected: bool
    configured: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "display_name": self.display_name,
            "connected": self.connected,
            "configured": self.configured,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RuntimeStatus:
    """Operational runtime signals (session continuity, not tool execution)."""

    titan_version: str
    active_project: str
    current_user: str
    current_phase: str
    progress: str
    last_user_message: str | None
    schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "titan_version": self.titan_version,
            "active_project": self.active_project,
            "current_user": self.current_user,
            "current_phase": self.current_phase,
            "progress": self.progress,
            "last_user_message": self.last_user_message,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class WorldBlocker:
    """Something preventing forward progress."""

    id: str
    source: str
    summary: str
    detail: str
    severity: float
    related_mission_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "summary": self.summary,
            "detail": self.detail,
            "severity": round(self.severity, 3),
            "related_mission_id": self.related_mission_id,
        }


@dataclass(frozen=True)
class WorldOpportunity:
    """Actionable improvement or quick win."""

    id: str
    source: str
    summary: str
    detail: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "summary": self.summary,
            "detail": self.detail,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class WorldRisk:
    """Potential negative outcome if ignored."""

    id: str
    source: str
    summary: str
    detail: str
    severity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "summary": self.summary,
            "detail": self.detail,
            "severity": round(self.severity, 3),
        }


@dataclass(frozen=True)
class ActiveFocus:
    """What Titan believes deserves attention right now."""

    mission_id: str | None
    mission_title: str | None
    mission_state: str | None
    recommended_mission_id: str | None
    recommended_mission_title: str | None
    should_switch_focus: bool
    reasoning: str
    user_goal_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_title": self.mission_title,
            "mission_state": self.mission_state,
            "recommended_mission_id": self.recommended_mission_id,
            "recommended_mission_title": self.recommended_mission_title,
            "should_switch_focus": self.should_switch_focus,
            "reasoning": self.reasoning,
            "user_goal_hints": list(self.user_goal_hints),
        }


@dataclass(frozen=True)
class ProjectState:
    """Project-centric slice of the world model."""

    active_projects: tuple[str, ...]
    project_health: tuple[ProjectHealth, ...]
    project_dependencies: dict[str, tuple[str, ...]]
    code_modules: tuple[str, ...]
    architectural_boundaries: tuple[str, ...]
    summary: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_projects": list(self.active_projects),
            "project_health": [item.to_dict() for item in self.project_health],
            "project_dependencies": {
                key: list(values) for key, values in self.project_dependencies.items()
            },
            "code_modules": list(self.code_modules),
            "architectural_boundaries": list(self.architectural_boundaries),
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class WorkspaceState:
    """Workspace-centric slice of the world model."""

    workspace_root: str
    current_project: str
    git_branch: str | None
    project_language: str
    open_files: tuple[str, ...]
    recently_modified_files: tuple[str, ...]
    documentation_files: tuple[str, ...]
    known_repositories: tuple[str, ...]
    summary: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "current_project": self.current_project,
            "git_branch": self.git_branch,
            "project_language": self.project_language,
            "open_files": list(self.open_files),
            "recently_modified_files": list(self.recently_modified_files),
            "documentation_files": list(self.documentation_files),
            "known_repositories": list(self.known_repositories),
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class WorldModelSnapshot:
    """Full structured representation of Titan's current environmental belief."""

    schema_version: int
    timestamp: datetime
    active_projects: tuple[str, ...]
    project_health: tuple[ProjectHealth, ...]
    project_dependencies: dict[str, tuple[str, ...]]
    open_tasks: tuple[TaskRecord, ...]
    completed_tasks: tuple[TaskRecord, ...]
    active_missions: tuple[dict[str, Any], ...]
    available_tools: tuple[ToolAvailability, ...]
    connected_integrations: tuple[IntegrationStatus, ...]
    runtime_status: RuntimeStatus
    current_workspace: WorkspaceState
    known_repositories: tuple[str, ...]
    documents: tuple[str, ...]
    code_modules: tuple[str, ...]
    user_goals: tuple[str, ...]
    current_focus: ActiveFocus
    blockers: tuple[WorldBlocker, ...]
    risks: tuple[WorldRisk, ...]
    opportunities: tuple[WorldOpportunity, ...]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp.isoformat(),
            "active_projects": list(self.active_projects),
            "project_health": [item.to_dict() for item in self.project_health],
            "project_dependencies": {
                key: list(values) for key, values in self.project_dependencies.items()
            },
            "open_tasks": [item.to_dict() for item in self.open_tasks],
            "completed_tasks": [item.to_dict() for item in self.completed_tasks],
            "active_missions": list(self.active_missions),
            "available_tools": [item.to_dict() for item in self.available_tools],
            "connected_integrations": [
                item.to_dict() for item in self.connected_integrations
            ],
            "runtime_status": self.runtime_status.to_dict(),
            "current_workspace": self.current_workspace.to_dict(),
            "known_repositories": list(self.known_repositories),
            "documents": list(self.documents),
            "code_modules": list(self.code_modules),
            "user_goals": list(self.user_goals),
            "current_focus": self.current_focus.to_dict(),
            "blockers": [item.to_dict() for item in self.blockers],
            "risks": [item.to_dict() for item in self.risks],
            "opportunities": [item.to_dict() for item in self.opportunities],
            "summary": self.summary,
        }

    def format_for_prompt(self) -> str:
        lines = [
            "WORLD MODEL",
            f"Generated: {self.timestamp.isoformat()}",
            f"Summary: {self.summary}",
            "",
            "ACTIVE PROJECTS",
            ", ".join(self.active_projects) or "(none)",
            "",
            "CURRENT FOCUS",
            self.current_focus.reasoning or "(no focus)",
            "",
            "BLOCKERS",
        ]
        if self.blockers:
            for blocker in self.blockers[:8]:
                lines.append(f"- [{blocker.source}] {blocker.summary}")
        else:
            lines.append("(none)")
        lines.extend(["", "OPPORTUNITIES"])
        if self.opportunities:
            for opp in self.opportunities[:8]:
                lines.append(f"- [{opp.source}] {opp.summary}")
        else:
            lines.append("(none)")
        lines.extend(
            [
                "",
                "OPEN TASKS",
                str(len(self.open_tasks)),
                "",
                "AVAILABLE TOOLS",
                str(len(self.available_tools)),
            ]
        )
        return "\n".join(lines)


class WorldModel:
    """Maintain Titan's structured belief about the current environment.

    Read-only aggregation over existing subsystems. Never executes actions.
    """

    def __init__(
        self,
        *,
        workspace_awareness: WorkspaceAwareness | None = None,
        executive_function: ExecutiveFunction | None = None,
        mission_manager: MissionManager | None = None,
        memory_service: MemoryService | None = None,
        context_manager: ContextManager | None = None,
        state_manager: StateManager | None = None,
        project_intelligence: ProjectIntelligence | None = None,
        code_intelligence: CodeIntelligence | None = None,
        developer_workflow: DeveloperWorkflow | None = None,
        knowledge_learning_engine: KnowledgeLearningEngine | None = None,
        proactive_intelligence: ProactiveIntelligence | None = None,
        tool_intelligence: ToolIntelligence | None = None,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._executive_function = executive_function
        self._mission_manager = mission_manager
        self._memory_service = memory_service
        self._context_manager = context_manager
        self._state_manager = state_manager
        self._project_intelligence = project_intelligence
        self._code_intelligence = code_intelligence
        self._developer_workflow = developer_workflow
        self._knowledge_learning_engine = knowledge_learning_engine
        self._proactive_intelligence = proactive_intelligence
        self._tool_intelligence = tool_intelligence
        self._snapshot: WorldModelSnapshot | None = None
        self._project_state: ProjectState | None = None
        self._workspace_state: WorkspaceState | None = None

    def build_world_model(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        refresh_workspace: bool = True,
    ) -> WorldModelSnapshot:
        """Aggregate all subsystem signals into a fresh world model snapshot."""
        timestamp = _utc_now()
        user, project_id = self._resolve_context(user, project_id)

        workspace = self._load_workspace(
            user=user,
            project_id=project_id,
            refresh=refresh_workspace,
        )
        executive = self._load_executive(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        architecture = self._load_architecture(
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive=executive,
        )
        missions = self._load_active_missions()
        open_tasks, completed_tasks = self._partition_tasks(missions)
        tools = self._load_tools()
        integrations = self._load_integrations(tools)
        runtime = self._load_runtime_status(user=user, project_id=project_id)
        workspace_state = self._build_workspace_state(workspace, timestamp)
        self._workspace_state = workspace_state

        active_projects = self._resolve_active_projects(
            workspace, project_id, architecture
        )
        project_health = self._assess_project_health(
            active_projects,
            executive=executive,
            architecture=architecture,
            workspace=workspace,
        )
        dependencies = self._load_dependencies(architecture)
        code_modules = self._load_code_modules(workspace, architecture)
        documents = workspace.documentation_files if workspace is not None else ()
        repositories = self._load_repositories(workspace)
        user_goals = self._load_user_goals(message, user=user, project_id=project_id)
        focus = self._build_active_focus(executive, user_goals)
        blockers = self._collect_blockers(executive, workspace, missions)
        risks = self._collect_risks(executive, architecture, workspace)
        opportunities = self._collect_opportunities(executive, workspace)

        project_state = ProjectState(
            active_projects=active_projects,
            project_health=project_health,
            project_dependencies=dependencies,
            code_modules=code_modules,
            architectural_boundaries=(
                architecture.architectural_boundaries if architecture else ()
            ),
            summary=architecture.summary if architecture else "",
            timestamp=timestamp,
        )
        self._project_state = project_state

        summary = self._build_summary(
            active_projects=active_projects,
            blockers=blockers,
            focus=focus,
            open_task_count=len(open_tasks),
            tool_count=len(tools),
        )

        snapshot = WorldModelSnapshot(
            schema_version=SCHEMA_VERSION,
            timestamp=timestamp,
            active_projects=active_projects,
            project_health=project_health,
            project_dependencies=dependencies,
            open_tasks=open_tasks,
            completed_tasks=completed_tasks,
            active_missions=self._missions_to_dicts(missions),
            available_tools=tools,
            connected_integrations=integrations,
            runtime_status=runtime,
            current_workspace=workspace_state,
            known_repositories=repositories,
            documents=documents,
            code_modules=code_modules,
            user_goals=user_goals,
            current_focus=focus,
            blockers=blockers,
            risks=risks,
            opportunities=opportunities,
            summary=summary,
        )
        self._snapshot = snapshot
        logger.debug("World model built: %s", summary)
        return snapshot

    def refresh(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> WorldModelSnapshot:
        """Rebuild the world model from current subsystem state."""
        return self.build_world_model(
            message,
            user=user,
            project_id=project_id,
            refresh_workspace=True,
        )

    def get_snapshot(self) -> WorldModelSnapshot:
        """Return the cached snapshot, building one if necessary."""
        if self._snapshot is None:
            return self.build_world_model()
        return self._snapshot

    def get_project_state(self) -> ProjectState:
        """Return the project-centric slice of the world model."""
        if self._project_state is None:
            self.build_world_model()
        assert self._project_state is not None
        return self._project_state

    def get_workspace_state(self) -> WorkspaceState:
        """Return the workspace-centric slice of the world model."""
        if self._workspace_state is None:
            self.build_world_model()
        assert self._workspace_state is not None
        return self._workspace_state

    def get_blockers(self) -> tuple[WorldBlocker, ...]:
        """Return known blockers from the latest snapshot."""
        return self.get_snapshot().blockers

    def get_opportunities(self) -> tuple[WorldOpportunity, ...]:
        """Return known opportunities from the latest snapshot."""
        return self.get_snapshot().opportunities

    def get_dependencies(self) -> dict[str, tuple[str, ...]]:
        """Return project dependency map from the latest snapshot."""
        return self.get_snapshot().project_dependencies

    def get_active_focus(self) -> ActiveFocus:
        """Return what Titan believes deserves attention right now."""
        return self.get_snapshot().current_focus

    def export_world_model(self) -> dict[str, Any]:
        """Export the full world model as JSON-serializable data."""
        snapshot = self.get_snapshot()
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": _utc_now().isoformat(),
            "world_model": snapshot.to_dict(),
        }

    # ------------------------------------------------------------------
    # Private helpers — read-only subsystem access
    # ------------------------------------------------------------------

    def _resolve_context(
        self,
        user: str | None,
        project_id: str | None,
    ) -> tuple[str, str | None]:
        resolved_user = user
        resolved_project = project_id
        if self._context_manager is not None:
            if resolved_user is None:
                resolved_user = self._context_manager.current_user
            if resolved_project is None:
                resolved_project = self._context_manager.active_project or None
        return resolved_user or "Nolan", resolved_project

    def _load_workspace(
        self,
        *,
        user: str,
        project_id: str | None,
        refresh: bool,
    ) -> WorkspaceSnapshot | None:
        if self._workspace_awareness is None:
            return None
        if refresh:
            return self._workspace_awareness.refresh(user=user, project_id=project_id)
        return self._workspace_awareness.get_workspace()

    def _load_executive(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
    ) -> ExecutiveEvaluation | None:
        if self._executive_function is None:
            return None
        return self._executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def _load_architecture(
        self,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        executive: ExecutiveEvaluation | None,
    ):
        if self._project_intelligence is None:
            return None
        return self._project_intelligence.analyze_project(
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=executive,
            refresh=True,
        )

    def _load_active_missions(self) -> tuple[Mission, ...]:
        if self._mission_manager is None:
            return ()
        return tuple(self._mission_manager.runtime.list_active_missions())

    def _partition_tasks(
        self,
        missions: tuple[Mission, ...],
    ) -> tuple[tuple[TaskRecord, ...], tuple[TaskRecord, ...]]:
        open_tasks: list[TaskRecord] = []
        completed_tasks: list[TaskRecord] = []
        open_states = {
            TaskState.PENDING,
            TaskState.IN_PROGRESS,
            TaskState.FAILED,
        }
        for mission in missions:
            for task in mission.tasks:
                record = TaskRecord(
                    task_id=task.id,
                    mission_id=mission.id,
                    mission_title=mission.title,
                    description=task.description,
                    state=task.state,
                    order=task.order,
                )
                if task.state in open_states:
                    open_tasks.append(record)
                elif task.state == TaskState.COMPLETED:
                    completed_tasks.append(record)
        open_tasks.sort(key=lambda item: (item.mission_id, item.order))
        completed_tasks.sort(key=lambda item: (item.mission_id, item.order))
        return tuple(open_tasks), tuple(completed_tasks)

    def _load_tools(self) -> tuple[ToolAvailability, ...]:
        if self._tool_intelligence is None:
            return ()
        records = self._tool_intelligence.list_capabilities()
        tools = [
            ToolAvailability(
                tool_id=record.id,
                display_name=record.display_name,
                enabled=record.enabled,
                category=record.category,
                risk_level=record.risk_level,
                requires_confirmation=record.requires_confirmation,
            )
            for record in records
        ]
        tools.sort(key=lambda item: item.tool_id)
        return tuple(tools)

    def _load_integrations(
        self,
        tools: tuple[ToolAvailability, ...],
    ) -> tuple[IntegrationStatus, ...]:
        tool_ids = {tool.tool_id for tool in tools}
        integrations: list[IntegrationStatus] = []

        def _add(
            integration_id: str,
            display_name: str,
            *,
            installed: bool,
            configured: bool,
            detail: str,
        ) -> None:
            integrations.append(
                IntegrationStatus(
                    integration_id=integration_id,
                    display_name=display_name,
                    connected=installed and configured,
                    configured=configured,
                    detail=detail,
                )
            )

        _add(
            "github",
            "GitHub",
            installed="github" in tool_ids,
            configured=TITAN_GITHUB_ENABLED,
            detail="Repository and PR integration via GitHub tool.",
        )
        _add(
            "obsidian",
            "Obsidian",
            installed="obsidian" in tool_ids,
            configured=TITAN_OBSIDIAN_ENABLED and TITAN_OBSIDIAN_VAULT_PATH is not None,
            detail=(
                f"Vault: {TITAN_OBSIDIAN_VAULT_PATH}"
                if TITAN_OBSIDIAN_VAULT_PATH is not None
                else "Vault path not configured.",
            ),
        )
        for tool_id in sorted(_INTEGRATION_TOOL_IDS - {"github", "obsidian"}):
            if tool_id in tool_ids:
                tool = next(item for item in tools if item.tool_id == tool_id)
                _add(
                    tool_id,
                    tool.display_name,
                    installed=True,
                    configured=tool.enabled,
                    detail=f"Installed tool ({tool.category}).",
                )
        return tuple(integrations)

    def _load_runtime_status(
        self,
        *,
        user: str,
        project_id: str | None,
    ) -> RuntimeStatus:
        state = {}
        if self._state_manager is not None:
            state = self._state_manager.get_state()
        phase = ""
        if self._context_manager is not None:
            phase = self._context_manager.current_phase or ""
        return RuntimeStatus(
            titan_version=VERSION,
            active_project=project_id or str(state.get("active_project", "Titan")),
            current_user=user,
            current_phase=phase,
            progress=str(state.get("progress", "")),
            last_user_message=state.get("last_user_message"),
            schema_version=SCHEMA_VERSION,
        )

    def _build_workspace_state(
        self,
        workspace: WorkspaceSnapshot | None,
        timestamp: datetime,
    ) -> WorkspaceState:
        if workspace is None:
            return WorkspaceState(
                workspace_root="",
                current_project="",
                git_branch=None,
                project_language="",
                open_files=(),
                recently_modified_files=(),
                documentation_files=(),
                known_repositories=(),
                summary="Workspace awareness unavailable.",
                timestamp=timestamp,
            )
        repositories = self._load_repositories(workspace)
        return WorkspaceState(
            workspace_root=workspace.workspace_root,
            current_project=workspace.current_project,
            git_branch=workspace.git_branch,
            project_language=workspace.project_language,
            open_files=workspace.open_files,
            recently_modified_files=workspace.recently_modified_files,
            documentation_files=workspace.documentation_files,
            known_repositories=repositories,
            summary=workspace.summary,
            timestamp=timestamp,
        )

    def _resolve_active_projects(
        self,
        workspace: WorkspaceSnapshot | None,
        project_id: str | None,
        architecture,
    ) -> tuple[str, ...]:
        projects: list[str] = []
        if project_id:
            projects.append(project_id)
        if workspace is not None:
            for name in workspace.projects:
                if name and name not in projects:
                    projects.append(name)
            if workspace.current_project and workspace.current_project not in projects:
                projects.append(workspace.current_project)
        if architecture is not None and architecture.project_name:
            if architecture.project_name not in projects:
                projects.append(architecture.project_name)
        return tuple(projects)

    def _assess_project_health(
        self,
        active_projects: tuple[str, ...],
        *,
        executive: ExecutiveEvaluation | None,
        architecture,
        workspace: WorkspaceSnapshot | None,
    ) -> tuple[ProjectHealth, ...]:
        if not active_projects:
            return ()

        blocked_count = len(executive.blocked_missions) if executive else 0
        idle_count = len(executive.idle_missions) if executive else 0
        violations = (
            len(architecture.dependency_graph.boundary_violations)
            if architecture is not None
            else 0
        )
        workspace_signals = len(workspace.recommendations) if workspace else 0

        score = 1.0
        signals: list[str] = []
        if blocked_count:
            score -= min(0.45, 0.15 * blocked_count)
            signals.append(f"{blocked_count} blocked mission(s)")
        if violations:
            score -= min(0.25, 0.05 * violations)
            signals.append(f"{violations} architecture boundary violation(s)")
        if idle_count:
            score -= min(0.15, 0.05 * idle_count)
            signals.append(f"{idle_count} idle mission(s)")
        if workspace_signals:
            score -= min(0.1, 0.02 * workspace_signals)
            signals.append(f"{workspace_signals} workspace advisory signal(s)")

        score = max(0.0, min(1.0, score))
        if blocked_count:
            status = ProjectHealthStatus.BLOCKED
        elif score < 0.55:
            status = ProjectHealthStatus.DEGRADED
        elif score < 0.8 or violations or workspace_signals:
            status = ProjectHealthStatus.ATTENTION
        elif score >= 0.8:
            status = ProjectHealthStatus.HEALTHY
        else:
            status = ProjectHealthStatus.UNKNOWN

        summary = (
            f"Health score {score:.2f} — {status.value}."
            if signals
            else f"Health score {score:.2f} — no major signals."
        )

        return tuple(
            ProjectHealth(
                project_id=project,
                status=status,
                score=score,
                summary=summary,
                signals=tuple(signals),
            )
            for project in active_projects
        )

    def _load_dependencies(self, architecture) -> dict[str, tuple[str, ...]]:
        if architecture is None:
            return {}
        graph = architecture.dependency_graph
        result: dict[str, tuple[str, ...]] = {}
        for node in graph.nodes:
            result[node] = graph.dependencies_of(node)
        return result

    def _load_code_modules(self, workspace, architecture) -> tuple[str, ...]:
        modules: list[str] = []
        if workspace is not None:
            modules.extend(workspace.detected_modules)
        if architecture is not None:
            for module in architecture.modules:
                name = module.name
                if name and name not in modules:
                    modules.append(name)
        return tuple(modules[:80])

    def _load_repositories(self, workspace: WorkspaceSnapshot | None) -> tuple[str, ...]:
        if workspace is None:
            return ()
        repos: list[str] = []
        root = workspace.workspace_root.strip()
        if root:
            repos.append(root)
        if workspace.git_branch:
            repos.append(f"{root} (branch: {workspace.git_branch})")
        return tuple(repos)

    def _load_user_goals(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
    ) -> tuple[str, ...]:
        goals: list[str] = []
        if self._memory_service is not None:
            retrieval = self._memory_service.retrieve(
                user,
                message or "goals projects focus",
                project_id=project_id,
            )
            for item in retrieval.items:
                text = str(item).strip()
                if text and text not in goals:
                    goals.append(text)
        if self._knowledge_learning_engine is not None:
            for item in self._knowledge_learning_engine.list_verified_knowledge(
                category=None,
            )[:5]:
                if item.title and item.title not in goals:
                    goals.append(item.title)
        return tuple(goals[:20])

    def _build_active_focus(
        self,
        executive: ExecutiveEvaluation | None,
        user_goals: tuple[str, ...],
    ) -> ActiveFocus:
        if executive is None:
            return ActiveFocus(
                mission_id=None,
                mission_title=None,
                mission_state=None,
                recommended_mission_id=None,
                recommended_mission_title=None,
                should_switch_focus=False,
                reasoning="Executive function unavailable.",
                user_goal_hints=user_goals[:5],
            )
        current = executive.current_mission
        recommendation = executive.recommendation
        return ActiveFocus(
            mission_id=current.id if current is not None else None,
            mission_title=current.title if current is not None else None,
            mission_state=current.state.value if current is not None else None,
            recommended_mission_id=recommendation.recommended_mission_id,
            recommended_mission_title=recommendation.recommended_title,
            should_switch_focus=recommendation.should_switch,
            reasoning=recommendation.reasoning or executive.reasoning,
            user_goal_hints=user_goals[:5],
        )

    def _collect_blockers(
        self,
        executive: ExecutiveEvaluation | None,
        workspace: WorkspaceSnapshot | None,
        missions: tuple[Mission, ...],
    ) -> tuple[WorldBlocker, ...]:
        blockers: list[WorldBlocker] = []

        if executive is not None:
            for index, evaluation in enumerate(executive.blocked_missions):
                blockers.append(
                    WorldBlocker(
                        id=f"executive-blocked-{evaluation.mission_id}",
                        source="executive_function",
                        summary=evaluation.title,
                        detail=evaluation.reasoning,
                        severity=min(1.0, 0.6 + evaluation.blocked_hours / 72.0),
                        related_mission_id=evaluation.mission_id,
                    )
                )

        for mission in missions:
            if mission.state == MissionState.BLOCKED:
                blockers.append(
                    WorldBlocker(
                        id=f"mission-blocked-{mission.id}",
                        source="mission_runtime",
                        summary=mission.title,
                        detail=f"Mission state: {mission.state.value}",
                        severity=0.85,
                        related_mission_id=mission.id,
                    )
                )

        if workspace is not None:
            for index, rec in enumerate(workspace.recommendations):
                if rec.kind in {"blocked", "risk", "missing_tests", "stale_docs"}:
                    blockers.append(
                        WorldBlocker(
                            id=f"workspace-{rec.kind}-{index}",
                            source="workspace_awareness",
                            summary=rec.summary,
                            detail=rec.detail,
                            severity=0.5,
                        )
                    )

        if self._proactive_intelligence is not None:
            digest = self._proactive_intelligence.get_digest()
            for rec in digest.recommendations:
                if rec.category.value.startswith("MISSION_BLOCKED"):
                    blockers.append(
                        WorldBlocker(
                            id=f"proactive-{rec.id}",
                            source="proactive_intelligence",
                            summary=rec.title,
                            detail=rec.summary,
                            severity=rec.confidence,
                            related_mission_id=rec.related_mission_id,
                        )
                    )

        return tuple(blockers)

    def _collect_risks(
        self,
        executive: ExecutiveEvaluation | None,
        architecture,
        workspace: WorkspaceSnapshot | None,
    ) -> tuple[WorldRisk, ...]:
        risks: list[WorldRisk] = []

        if architecture is not None:
            for index, violation in enumerate(
                architecture.dependency_graph.boundary_violations[:10]
            ):
                risks.append(
                    WorldRisk(
                        id=f"arch-violation-{index}",
                        source="project_intelligence",
                        summary="Architecture boundary violation",
                        detail=violation,
                        severity=0.7,
                    )
                )

        if executive is not None:
            for index, evaluation in enumerate(executive.idle_missions[:5]):
                risks.append(
                    WorldRisk(
                        id=f"idle-mission-{evaluation.mission_id}",
                        source="executive_function",
                        summary=f"Idle mission: {evaluation.title}",
                        detail=evaluation.reasoning,
                        severity=0.45,
                    )
                )

        if workspace is not None:
            for index, rec in enumerate(workspace.recommendations):
                if rec.kind in {"large_change", "undocumented", "stale_docs"}:
                    risks.append(
                        WorldRisk(
                            id=f"workspace-risk-{index}",
                            source="workspace_awareness",
                            summary=rec.summary,
                            detail=rec.detail,
                            severity=0.4,
                        )
                    )

        return tuple(risks)

    def _collect_opportunities(
        self,
        executive: ExecutiveEvaluation | None,
        workspace: WorkspaceSnapshot | None,
    ) -> tuple[WorldOpportunity, ...]:
        opportunities: list[WorldOpportunity] = []

        if executive is not None and executive.recommended_next_mission is not None:
            nxt = executive.recommended_next_mission
            opportunities.append(
                WorldOpportunity(
                    id=f"focus-{nxt.mission_id}",
                    source="executive_function",
                    summary=f"Recommended focus: {nxt.title}",
                    detail=nxt.reasoning,
                    confidence=min(1.0, nxt.priority_score / 100.0),
                )
            )

        if workspace is not None:
            for index, rec in enumerate(workspace.recommendations):
                if rec.kind in {"quick_win", "documentation", "opportunity"}:
                    opportunities.append(
                        WorldOpportunity(
                            id=f"workspace-opp-{index}",
                            source="workspace_awareness",
                            summary=rec.summary,
                            detail=rec.detail,
                            confidence=0.55,
                        )
                    )

        if self._proactive_intelligence is not None:
            digest = self._proactive_intelligence.get_digest()
            for rec in digest.recommendations:
                if "OPPORTUNITY" in rec.category.value or "QUICK_WIN" in rec.category.value:
                    opportunities.append(
                        WorldOpportunity(
                            id=f"proactive-opp-{rec.id}",
                            source="proactive_intelligence",
                            summary=rec.title,
                            detail=rec.summary,
                            confidence=rec.confidence,
                        )
                    )

        if self._knowledge_learning_engine is not None:
            for index, item in enumerate(
                self._knowledge_learning_engine.list_verified_knowledge()[:3]
            ):
                opportunities.append(
                    WorldOpportunity(
                        id=f"knowledge-{item.id}",
                        source="knowledge_learning_engine",
                        summary=item.title,
                        detail=item.description,
                        confidence=item.confidence,
                    )
                )

        return tuple(opportunities)

    def _missions_to_dicts(self, missions: tuple[Mission, ...]) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": mission.id,
                "title": mission.title,
                "objective": mission.objective,
                "state": mission.state.value,
                "priority": mission.priority.value,
                "progress_percent": mission.progress_percent,
                "current_step": mission.current_step,
            }
            for mission in missions
        )

    def _build_summary(
        self,
        *,
        active_projects: tuple[str, ...],
        blockers: tuple[WorldBlocker, ...],
        focus: ActiveFocus,
        open_task_count: int,
        tool_count: int,
    ) -> str:
        project_label = active_projects[0] if active_projects else "no active project"
        focus_label = focus.mission_title or focus.recommended_mission_title or "unset"
        return (
            f"World model for {project_label}: focus={focus_label}, "
            f"{open_task_count} open task(s), {len(blockers)} blocker(s), "
            f"{tool_count} tool(s) available."
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
